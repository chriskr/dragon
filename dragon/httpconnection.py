import asyncore
from dragon.websocket13 import TestWebSocket13
import sys
import shlex
import json
from time import time
from os import stat, listdir
from os.path import isfile, isdir
from os.path import exists as path_exists
from os.path import join as path_join
from mimetypes import types_map
from .common import *
from .common import __version__ as VERSION

types_map[".manifest"] = "text/cache-manifest"
types_map[".ico"] = "image/x-icon"
types_map[".json"] = "application/json"
types_map[".xml"] = "application/xhtml+xml"


class HTTPConnection(asyncore.dispatcher):
    """To provide a simple HTTP response handler.
    Special methods can be implementd by subclassing this class
    """

    def __init__(self, conn, addr, context):
        asyncore.dispatcher.__init__(self, sock=conn)
        self.addr = addr
        self.context = context
        self.in_buffer = b""
        self.out_buffer = b""
        self.content_length = 0
        self.check_input = self.read_headers
        self.query = ''
        self.raw_post_data = ""
        # Timeout acts also as flag to signal
        # a connection which still waits for a response
        self.timeout = 0
        self.cgi_enabled = context.cgi_enabled
        self.cgi_script = ""
        self.GET_handlers = context.http_get_handlers

    def read_headers(self):
        raw_parsed_headers = parse_headers(self.in_buffer)
        if raw_parsed_headers:
            # to dispatch any hanging timeout response
            self.flush()
            (headers_raw, first_line,
             self.headers, self.in_buffer) = raw_parsed_headers
            method, path, protocol = first_line.split(BLANK, 2)
            # if path == "/app/":
            #    path = "/app/stp-1/client-en.xml"
            self.REQUEST_URI = path
            path = path.lstrip(b"/")
            if b"?" in path:
                path, self.query = path.split(b'?', 1)
            arguments = path.split(b"/")
            command = (arguments and arguments.pop(0) or b"").decode()
            command = command.replace('-', '_').replace('.', '_')
            system_path = URI_to_system_path(path.rstrip(b"/")) or "."
            self.method = method
            self.path = path
            self.command = command
            self.arguments = arguments
            self.system_path = system_path
            self.timeout = time() + TIMEOUT
            # if not self.REQUEST_URI.endswith("services"):
            #    print self.REQUEST_URI
            if self.cgi_enabled:
                self.check_is_cgi(system_path)
            # POST
            if method == "POST":
                if "Content-Length" in self.headers:
                    self.content_length = int(self.headers["Content-Length"])
                    self.check_input = self.read_content
                    self.check_input()
            # GET
            elif method == b"GET":
                if hasattr(self, command) and \
                        hasattr(getattr(self, command), '__call__'):
                    getattr(self, command)()
                elif command in self.GET_handlers:
                    self.out_buffer += self.GET_handlers[command](self.headers)
                    self.timeout = 0
                else:
                    if self.cgi_script:
                        self.handle_cgi()
                    elif os.path.exists(system_path) or not path:
                        self.serve(path, system_path)
                    # favicon.ico and device-favicon.png
                    elif path_exists(path_join(SOURCE_ROOT, system_path)):
                        self.serve(path, path_join(SOURCE_ROOT, system_path))
                    else:
                        content = "The server cannot handle: %s" % path
                        self.out_buffer += NOT_FOUND % (
                            get_timestamp(),
                            len(content),
                            content)
                        self.timeout = 0
                if self.in_buffer:
                    self.check_input()
            # Not implemented method
            else:
                content = b"The server cannot handle: %s" % method
                self.out_buffer += NOT_FOUND % (
                    get_timestamp(),
                    str.encode(str(len(content))),
                    content)
                self.timeout = 0

    def read_content(self):
        if len(self.in_buffer) >= self.content_length:
            self.raw_post_data = self.in_buffer[0:self.content_length]
            if self.cgi_script:
                self.handle_cgi()
            elif hasattr(self, self.command):
                getattr(self, self.command)()
            else:
                content = "The server cannot handle: %s" % self.path
                self.out_buffer += NOT_FOUND % (
                    get_timestamp(),
                    len(content),
                    content)
            self.raw_post_data = ""
            self.in_buffer = self.in_buffer[self.content_length:]
            self.content_length = 0
            self.check_input = self.read_headers
            if self.in_buffer:
                self.check_input()

    def serve(self, path, system_path):
        if path_exists(system_path) or path == b"":
            if isfile(system_path):
                self.serve_file(path, system_path)
            elif isdir(system_path) or path == b"":
                self.serve_dir(path, system_path)
        else:
            content = "The sever couldn't find %s" % system_path
            self.out_buffer += NOT_FOUND % (
                get_timestamp(),
                len(content),
                content)
            self.timeout = 0

    def serve_file(self, path, system_path):
        if b"If-Modified-Since" in self.headers and \
           timestamp_to_time(self.headers[b"If-Modified-Since"].decode()) >= \
           int(stat(system_path).st_mtime):
            self.out_buffer += NOT_MODIFIED % get_timestamp()
            self.timeout = 0
        else:
            ending = (b"." in path and path[path.rfind(
                b"."):] or b"no-ending").decode()
            mime = str.encode(
                ending in types_map and types_map[ending] or 'text/plain')
            try:
                response_template = RESPONSE_OK_CONTENT
                if isfile(system_path + '.gz'):
                    response_template = RESPONSE_OK_CONTENT_GZIP
                    system_path += '.gz'
                f = open(system_path, 'rb')
                content = f.read()
                f.close()
                self.out_buffer += response_template % (
                    get_timestamp(),
                    b'Last-Modified: %s%s' % (
                        get_timestamp(system_path),
                        CRLF),
                    mime,
                    str.encode(str(len(content))),
                    content)
                self.timeout = 0
            except:
                content = "The server cannot find %s" % system_path
                self.out_buffer += NOT_FOUND % (
                    get_timestamp(),
                    len(content),
                    content)
                self.timeout = 0

    def serve_dir(self, path, system_path):
        if path and not path.endswith(b'/'):
            self.out_buffer += REDIRECT % (get_timestamp(), path + b'/')
            self.timeout = 0
        else:
            try:
                items_dir = [item for item in listdir(system_path)
                             if isdir(path_join(system_path, item))]
                items_file = [item for item in listdir(system_path)
                              if isfile(path_join(system_path, item))]
                items_dir.sort()
                items_file.sort()
                if path:
                    items_dir.insert(0, '..')
                markup = [ITEM_DIR % (str.encode(quote(item)), str.encode(item))
                          for item in items_dir]
                markup.extend([ITEM_FILE % (str.encode(quote(item)), str.encode(item))
                               for item in items_file])
                content = DIR_VIEW % (b"".join(markup))
            except Exception as msg:
                print("OS error: {0}".format(msg))
                content = DIR_VIEW % str.encode(
                    """<li style="color:#f30">%s</li>""" % (msg))
            self.out_buffer += RESPONSE_OK_CONTENT % (
                get_timestamp(),
                b'',
                b"text/html",
                str.encode(str(len(content))),
                content)
            self.timeout = 0

    def test_web_sock_13(self):
        if self.headers.get(b"Upgrade") == b"websocket":
            self.del_channel()
            self.timeout = 0
            TestWebSocket13(self.socket,
                            self.headers,
                            self.in_buffer,
                            self.path)
        else:
            self.out_buffer += BAD_REQUEST % get_timestamp()
            self.timeout = 0

    # ============================================================
    #
    # ============================================================
    def flush(self):
        pass
    # ============================================================
    # Implementations of the asyncore.dispatcher class methods
    # ============================================================

    def handle_read(self):
        self.in_buffer += self.recv(BUFFERSIZE)
        self.check_input()

    def writable(self):
        return bool(self.out_buffer)

    def handle_write(self):
        sent = self.send(self.out_buffer)
        self.out_buffer = self.out_buffer[sent:]

    def handle_close(self):
        self.close()
