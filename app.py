"""
Websocket proxy with string replacement
"""
import os
import queue
import sys
from urllib import parse

from autobahn.twisted.websocket import WebSocketClientFactory
from autobahn.twisted.websocket import WebSocketClientProtocol
from autobahn.twisted.websocket import WebSocketServerFactory
from autobahn.twisted.websocket import WebSocketServerProtocol
from autobahn.twisted.websocket import connectWS
from dotenv import load_dotenv
from OpenSSL import crypto
from twisted.internet import reactor
from twisted.internet import ssl
from twisted.python import log


class WebsocketInfoServerProtocol(
    WebSocketServerProtocol
):  # pylint: disable=too-many-ancestors
    """
    This is the "server" protocol answering to incoming client connections
    """

    proxyfactory = None
    request = None

    def onConnect(self, request):
        """
        Websocket (not HTTP) connection start
        """
        self.request = request
        print("Client connecting: {0}".format(self.request))
        # this might be a valid request, so we'll start a BACKEND connection
        backendurl = os.environ.get("BACKEND")
        if self.request.params:
            # add the GET parameters to the backend request
            backendurl += "?" + parse.urlencode(self.request.params, doseq=True)
        print(
            "{1}: starting proxy backend connection attempt: {0}".format(
                backendurl, self.request.peer
            )
        )
        self.proxyfactory = WebSocketClientFactory(url=backendurl)
        self.proxyfactory.setProtocolOptions(autoPingInterval=10, autoPingTimeout=3)
        self.proxyfactory.protocol = WebsocketInfoProxyProtocol
        self.proxyfactory.proxyproto = None
        # this will be None until the connection to BACKEND
        # is successfully connected
        self.proxyfactory.messagecache = None
        self.proxyfactory.clientconnection = self
        sslfactory = None
        if os.environ.get("SSL_CLIENT_CERT", False) and os.environ.get(
            "SSL_CLIENT_KEY", False
        ):
            cert = ssl.Certificate.loadPEM(os.environ.get("SSL_CLIENT_CERT"))
            key = ssl.KeyPair.load(
                os.environ.get("SSL_CLIENT_KEY"), crypto.FILETYPE_PEM
            )
            privatecert = ssl.PrivateCertificate.fromCertificateAndKeyPair(cert, key)
            print("{1}: loaded client cert {0}".format(privatecert, self.request.peer))
            if os.environ.get("SSL_CLIENT_CA", False):
                cacerts = ssl.Certificate.loadPEM(os.environ.get("SSL_CLIENT_CA"))
                print("{1}: CA cert {0}".format(cacerts, self.request.peer))
                sslfactory = privatecert.options(cacerts)
            else:
                sslfactory = privatecert.options()
        connectWS(self.proxyfactory, contextFactory=sslfactory)

    def onOpen(self):
        """
        When the websocket connection open
        """
        print("{0}: Client WebSocket connection open.".format(self.request.peer))

    def onMessage(self, payload, isBinary):
        """
        when the client sends data forward to BACKEND
        """

        if (
            self.proxyfactory.proxyproto is not None
            and self.proxyfactory.messagecache is None
        ):
            # we are connected and there is no queue -> we'll send directly
            self.proxyfactory.proxyproto.sendMessage(payload)
            print(
                "{0}: client message forwarded: {1}".format(self.request.peer, payload)
            )
        else:
            # we received the first message before the connection to BACKEND
            # is established
            # or there is an existing cache that is yet to be purged
            # -> we'll cache the message and try to forward it later
            if self.proxyfactory.messagecache is None:
                self.proxyfactory.messagecache = queue.Queue()
            self.proxyfactory.messagecache.put(payload)
            print("{0}: client message queued: {1}".format(self.request.peer, payload))

    def onClose(self, wasClean, code, reason):
        """
        When the client closes the connection also close the BACKEND
        """
        if self.request is None:
            peer = None
        else:
            peer = self.request.peer
        print(
            "{1}: Client connection closed: code: {2}, reason: {0}".format(
                reason, peer, code
            )
        )
        # the client websocket upgrade might not have happened or
        # the backend connection might never have been opened/established
        if self.proxyfactory is not None and self.proxyfactory.proxyproto is not None:
            self.proxyfactory.proxyproto.sendClose()


class WebsocketInfoProxyProtocol(
    WebSocketClientProtocol
):  # pylint: disable=too-many-ancestors
    """
    This is the "client" protocol talking to the BACKEND server
    """

    factory = None  # will be set by WebSocketClientFactory when instantiating

    def onConnect(self, response):
        """
        Update the originating factory with a reference to this protocol
        for the "server protocol" corresponding to "our" client connection
        to be able to send data to this BACKEND connection
        If we never successfully connect this remains None and the server
        protocol will queue the incoming requests
        """
        self.factory.proxyproto = self
        print(
            "{1}: backend connecting: {0}".format(
                response.peer, self.factory.clientconnection.request.peer
            )
        )

    def onOpen(self):
        print(
            "{0}: backend WebSocket connection open.".format(
                self.factory.clientconnection.request.peer
            )
        )
        if self.factory.messagecache is not None:
            # there are messages waiting to be delivered
            while True:
                try:
                    message = self.factory.messagecache.get(block=False)
                    self.sendMessage(message)
                    print(
                        "{0}: sent queued message: {1}".format(
                            self.factory.clientconnection.request.peer, message
                        )
                    )
                except queue.Empty:
                    break
            self.factory.messagecache = None  # mark the cache as delivered

    def onMessage(self, payload, isBinary):
        """
        If we get data from BACKEND forward it to our client connection,
        performing string replacement if requested
        """

        if isBinary:
            print(
                "{1}: backend Binary message received: {0} bytes".format(
                    len(payload), self.factory.clientconnection.request.peer
                )
            )
        else:
            print(
                "{1}: backend Text message received: {0}".format(
                    payload.decode("utf8"), self.factory.clientconnection.request.peer
                )
            )
        message = payload.decode("utf8")
        message = message.replace(
            os.environ.get("OLD_HOST", ""), os.environ.get("NEW_HOST", "")
        )
        self.factory.clientconnection.sendMessage(message.encode("utf8"))

    def onClose(self, wasClean, code, reason):
        """
        If the BACKEND connection gets closed also close the client connection
        """
        print(
            "{1}: backend WebSocket connection closed: {0}".format(
                reason, self.factory.clientconnection.request.peer
            )
        )
        self.factory.clientconnection.sendClose()


if __name__ == "__main__":

    load_dotenv()
    log.startLogging(sys.stdout)
    # txaio.start_logging(level="debug")

    FACTORY = WebSocketServerFactory()
    FACTORY.protocol = WebsocketInfoServerProtocol
    FACTORY.setProtocolOptions(
        autoPingInterval=10, autoPingTimeout=3, trustXForwardedFor=1
    )

    reactor.listenTCP(os.environ.get("PORT", 8080), FACTORY)
    reactor.run()
