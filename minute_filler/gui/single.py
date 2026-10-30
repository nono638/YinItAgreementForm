"""One window at a time: a second launch hands its files to the copy already running and quits.

Two copies of the app open at once can lose work: both save settings.json (the last one wins), both can
add takes to the same run sheet and one copy's rows are lost, and both write the log. People open a second
copy by accident, double-clicking the icon again while the first is still starting, or with "Open with" on
a PDF while a window is open (with several files selected, Windows starts one launch per file, all at once).

The first copy takes a named mutex (Windows: one name per user, made or found in one step, so two launches
at the same moment can't both be first; it goes with the process, so a crash leaves nothing behind), then
listens on a local socket of the same name (a named pipe). A later launch finds the mutex, connects (the
first copy may still be starting and not listen yet), sends the files it was given ([] = just "show
yourself"), waits for "ok", says "go" and exits. The running copy answers from its event loop, which waits
while it builds its window or makes files on the window's thread, so a launch waits up to WAIT_MS for it.
When it still doesn't answer (hung), the new copy opens its own window rather than refuse to start. The
headless --batch and --selftest runs never take part.

The files are taken only on "go", which the launch says once it has read the "ok", so a launch is either
handed over or opens its own window, never both: a launch that gave up waiting has left its line in the pipe,
and a copy that comes back to life answers it "ok" to nobody (no "go": dropped; before, it opened the files
in a second window). Both ends are always the same version (the one installed app), so the steps need no
fallback for an older copy. While the running copy is closing (hold, then close), a launch is not answered:
it opens its own window rather than hand its files to a window about to go.

Windows pipes move data only while the event loop runs, so the running copy reads each launch's line as it
arrives (readyRead) and the launch runs the event loop while it waits (_wait); that also lets a test play
both parts in one process.
"""
from __future__ import annotations

import getpass
import json
import re
from typing import Callable

from PySide6.QtCore import QElapsedTimer, QEventLoop, QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

TIMEOUT_MS = 1500  # without a mutex (not Windows): how long to look for a copy that may not be there
WAIT_MS = 15000    # a copy runs (its mutex says so): to reach it, and again for its answer, while it starts or works
GO_MS = 5000       # the running copy, after its "ok": how long it waits for the launch's "go" (said at once)
ERROR_ALREADY_EXISTS = 183  # GetLastError after CreateMutexW: the mutex was there already (another copy runs)


def socket_name(app: str = "YinItAgreementForm") -> str:
    """The socket's (and mutex's) name: the app and the user, so two Windows accounts each get their own window."""
    user = re.sub(r"[^A-Za-z0-9_-]", "_", getpass.getuser() or "user")
    return f"{app}-{user}"


def _wait(ms: int, sock: QLocalSocket | None = None) -> None:
    """Waits up to `ms` with the event loop running, which moves the pipe's bytes along; with `sock`, only until
    it has news (data, or the other end gone). QCoreApplication.processEvents(flags, ms) would not do: it returns
    at once when nothing is pending, so a loop around it spins at full speed."""
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    if sock is not None:
        sock.readyRead.connect(loop.quit)
        sock.disconnected.connect(loop.quit)
    timer.start(ms)
    loop.exec()
    timer.stop()
    if sock is not None:
        sock.readyRead.disconnect(loop.quit)
        sock.disconnected.disconnect(loop.quit)


class SingleInstance(QObject):
    """claim() makes this copy the one that runs (True), or finds one running already (False); then
    send(files) hands that copy the files, and the running copy gets them (deliver, files_received)."""

    files_received = Signal(list)  # the paths another launch was given; [] when it was started bare

    def __init__(self, name: str = "", parent: QObject | None = None):
        super().__init__(parent)
        self.name = name or socket_name()
        self.server: QLocalServer | None = None
        self._peer: QLocalSocket | None = None  # the running copy, when claim() found it by its socket
        self._mutex = None                      # this copy's mutex handle, kept while it runs
        self._found_mutex = False               # claim() found another copy's mutex
        self._pending: list[list[str]] | None = []  # files that came before deliver(); None once delivering
        self._launches: list[_Launch] = []      # launches connected and not yet done with (answered, or held)
        self._holding = False                   # hold(): launches are read but not answered (the window closing)

    def claim(self) -> bool:
        """True when this copy is the first, and now listens; False when another copy runs (or is starting)."""
        first = self._take_mutex()
        if first is False:
            self._found_mutex = True
            return False
        if first is None:  # no mutex here: is a copy listening?
            probe = QLocalSocket(self)
            probe.connectToServer(self.name)
            if probe.waitForConnected(TIMEOUT_MS):
                self._peer = probe  # kept for send(): one connection, one message
                return False
        self._listen()
        return True

    def _take_mutex(self) -> bool | None:
        """Makes the mutex "Local\\<name>": True when this copy made it, False when another copy of this user's
        has it, None when there is no such thing (not Windows) or it failed."""
        try:
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        except (ImportError, AttributeError, OSError):
            return None
        k32.CreateMutexW.restype = wintypes.HANDLE
        k32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = k32.CreateMutexW(None, False, "Local\\" + self.name)
        if not handle:
            return None
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            k32.CloseHandle(handle)
            return False
        self._mutex = (k32, handle)
        return True

    def _listen(self) -> None:
        """Listens on the socket for later launches; one that can't listen runs anyway, as a copy on its own."""
        QLocalServer.removeServer(self.name)  # a name left behind (not on Windows, but harmless)
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._take)
        if not self.server.listen(self.name):
            self.server = None

    def send(self, files: list[str]) -> bool:
        """Hands `files` to the copy running, waits for its "ok" and says "go" (the copy takes the files only
        then); False when it doesn't answer, or "go" couldn't be said (then this launch runs as usual, and the
        copy drops them). A copy found by its mutex is given WAIT_MS to listen and again to answer."""
        wait = WAIT_MS if self._found_mutex else TIMEOUT_MS
        clock = QElapsedTimer()
        clock.start()
        sock, self._peer = self._peer, None
        while sock is None:  # (it may still be starting: try again until it listens)
            attempt = QLocalSocket()  # (no parent: an attempt that failed is freed with its name)
            attempt.connectToServer(self.name)
            if attempt.waitForConnected(min(500, wait)):
                sock = attempt
            elif clock.elapsed() >= wait:
                return False
            else:
                _wait(100)
        try:  # let the running copy come to the front: Windows passes that right on only from the active process
            import ctypes
            ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
        except Exception:
            pass
        sock.write((json.dumps({"files": list(files)}) + "\n").encode("utf-8"))
        sock.flush()
        clock.restart()
        while not sock.canReadLine() and clock.elapsed() < wait \
                and sock.state() == QLocalSocket.LocalSocketState.ConnectedState:
            _wait(min(250, max(1, wait - clock.elapsed())), sock)
        ok = sock.canReadLine() and bytes(sock.readLine()).strip() == b"ok"
        if ok and sock.state() == QLocalSocket.LocalSocketState.ConnectedState:
            # (written before this launch quits: a "go" still in this process's buffer would be lost with it)
            sock.write(b"go\n")
            ok = sock.waitForBytesWritten(min(WAIT_MS, 2000)) or not sock.bytesToWrite()
        else:
            ok = False
        sock.disconnectFromServer()
        return bool(ok)

    def deliver(self, slot: Callable[[list], None]) -> None:
        """From now on the files of other launches go to slot (through files_received), and those that came
        before it was ready, while the window was being built, go to it at once."""
        self.files_received.connect(slot)
        pending, self._pending = self._pending or [], None
        for files in pending:
            slot(files)

    def _take(self) -> None:
        """A launch connected: its line is read as it arrives, then answered, and its files taken on its "go"
        (_Launch; a connection that says nothing, such as a probe that gave up, is dropped once it goes)."""
        while self.server and self.server.hasPendingConnections():
            _Launch(self, self.server.nextPendingConnection())  # (it adds itself to _launches)

    def _done(self, launch: "_Launch", line: bytes | None) -> None:
        """A launch is over: with its line (it said "go"), its files are passed on (kept for deliver() until the
        window is ready); None, dropped. A line that isn't the app's (no "files" list) passes nothing on."""
        if launch in self._launches:
            self._launches.remove(launch)
        if line is None:
            return
        try:
            files = json.loads(line.decode("utf-8")).get("files", [])
        except (ValueError, AttributeError):
            return
        if not isinstance(files, list):
            return
        files = [f for f in files if isinstance(f, str)]
        if self._pending is not None:
            self._pending.append(files)
        self.files_received.emit(files)

    def hold(self, on: bool = True) -> None:
        """While on, launches are read but not answered: the window is closing (its "Close anyway?" on screen)
        and files handed to it now would be lost with it. Off (the close called off) answers those waiting, as
        usual; close() leaves them unanswered, and each opens a window of its own."""
        self._holding = on
        if not on:
            for launch in list(self._launches):
                if launch.line is not None and not launch.answered:
                    launch.answer()

    def close(self) -> None:
        """Stops listening and lets the mutex go, so that a launch while this copy is shutting down opens a
        window of its own instead of waiting for this one (both would go with the process anyway). The launches
        connected and not done with are cut off (unanswered, they open their own windows at once rather than
        wait WAIT_MS for an answer that won't come)."""
        self._holding = True
        for launch in list(self._launches):
            launch.finish(False)
        if self.server:
            self.server.close()
            self.server = None
        if self._mutex:
            k32, handle = self._mutex
            k32.CloseHandle(handle)
            self._mutex = None


class _Launch:
    """One launch connected to the running copy, step by step: its line is read, answered "ok" (unless the copy
    holds: then once it lets go), and its files passed on when it says "go" (SingleInstance._done). One that goes
    before its "go" (it gave up waiting, and opens its own window), says something else, or says nothing within
    GO_MS of the "ok" is dropped. A plain object, not a QObject: it may be let go of from its own timer's signal,
    which a QObject must not be deleted in (the timer is the socket's, deleted later with it)."""

    def __init__(self, owner: SingleInstance, conn: QLocalSocket):
        self.owner, self.conn = owner, conn
        self.buf = bytearray()
        self.line: bytes | None = None  # the launch's line of files, once read
        self.answered = False           # "ok" said: its "go" is waited for
        self.timer = QTimer(conn)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._expire)
        conn.readyRead.connect(self._read)
        conn.disconnected.connect(self._gone)
        owner._launches.append(self)  # (before the first read: one gone already is done with at once)
        if conn.bytesAvailable():
            self._read()
        if self.conn is not None and conn.state() == QLocalSocket.LocalSocketState.UnconnectedState:
            self.finish(False)  # (it hung up before it was taken: no disconnected signal to come)

    def _read(self) -> None:
        """Takes the lines that came: the first is the files (answered at once, unless the copy holds), the next
        must be "go"."""
        if self.conn is None:
            return
        self.buf += bytes(self.conn.readAll())
        while self.conn is not None and b"\n" in self.buf:
            line, _, rest = bytes(self.buf).partition(b"\n")
            self.buf[:] = rest
            if self.line is None:
                self.line = line
                if not self.owner._holding:
                    self.answer()
            else:
                self.finish(self.answered and line.strip() == b"go")

    def answer(self) -> None:
        """Says "ok" and waits GO_MS for the "go"; a launch gone meanwhile is dropped."""
        if self.conn is None or self.answered:
            return
        if self.conn.state() != QLocalSocket.LocalSocketState.ConnectedState:
            self.finish(False)
            return
        self.answered = True
        self.conn.write(b"ok\n")
        self.conn.flush()
        self.timer.start(GO_MS)

    def _expire(self) -> None:
        """No "go" in GO_MS: one that came while this copy was busy is read first (its readyRead may be behind
        the timer), else the launch is dropped."""
        if self.conn is not None and self.conn.waitForReadyRead(100):
            self._read()
        if self.conn is not None:
            self.finish(False)

    def _gone(self) -> None:
        """The launch hung up: after its "go" (they can come together) it is done, else dropped."""
        self._read()
        if self.conn is not None:
            self.finish(False)

    def finish(self, deliver: bool) -> None:
        """Done with the launch: hangs up (after the "ok", if it is still being written) and tells the owner,
        with its line when it said "go" (deliver)."""
        conn, self.conn = self.conn, None
        if conn is None:
            return
        self.timer.stop()
        conn.readyRead.disconnect(self._read)
        conn.disconnected.disconnect(self._gone)
        if deliver and conn.state() != QLocalSocket.LocalSocketState.UnconnectedState:
            conn.disconnected.connect(conn.deleteLater)
            conn.disconnectFromServer()
        else:
            conn.abort()  # (unanswered, or no "go": at once, so a launch still waiting opens its window now)
            conn.deleteLater()
        self.owner._done(self, self.line if deliver else None)


def hand_over(single: SingleInstance, files: list[str]) -> bool:
    """What a launch does before opening a window: True when another copy runs and took the files (this
    launch should quit), False when this launch is the one to open the window."""
    if single.claim():
        return False
    return single.send(files)
