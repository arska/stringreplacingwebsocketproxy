"""
Websocket proxy with string replacement
"""
from autobahn.twisted.websocket import WebSocketServerProtocol, WebSocketServerFactory
from autobahn.twisted.websocket import WebSocketClientProtocol, WebSocketClientFactory
from autobahn.twisted.websocket import connectWS
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.internet import ssl
import time
import txaio
from dotenv import load_dotenv
import os
from OpenSSL import crypto


class WebsocketInfoServerProtocol(WebSocketServerProtocol):
    """
    This is the "server" protocol answering to incoming client connections
    """

    proxyfactory = None

    def onConnect(self, request):
        """
        Websocket (not HTTP) connection start
        """
        self.request = request
        print("Client connecting: {0}".format(self.request))
        # this might be a valid request, so we'll start a BACKEND connection
        print(
            "{1}: starting proxy backend connection attempt: {0}".format(
                os.environ.get("BACKEND"), self.request.peer
            )
        )
        self.proxyfactory = WebSocketClientFactory(url=os.environ.get("BACKEND"))
        self.proxyfactory.setProtocolOptions(autoPingInterval=10, autoPingTimeout=3)
        self.proxyfactory.protocol = WebsocketInfoProxyProtocol
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

        if isBinary:
            print(
                "{1}: Client Binary message received: {0} bytes".format(len(payload)),
                self.request.peer,
            )
        else:
            print(
                "{1}: Client Text message received: {0}".format(
                    payload.decode("utf8"), self.request.peer
                )
            )
        self.proxyfactory.proxyproto.sendMessage(payload)

    def onClose(self, wasClean, code, reason):
        """
        When the client closes the connection also close the BACKEND
        """
        print(
            "{1}: Client connection closed with reason: {0}".format(
                reason, self.request.peer
            )
        )
        # the backend connection might never have been opened
        if self.proxyfactory is not None:
            self.proxyfactory.proxyproto.sendClose()


class WebsocketInfoProxyProtocol(WebSocketClientProtocol):
    """
    This is the "client" protocol talking to the BACKEND server
    """

    def onConnect(self, request):
        """
        Update the originating factory with a reference to this protocol for the "server protocol" corresponding to "our" client connection to be able to send data to this BACKEND connection
        If we never successfully connect this remains None and the server protocol will of course throw errors
        """
        print(
            "{1}: backend connecting: {0}".format(
                request.peer, self.factory.clientconnection.request.peer
            )
        )
        self.factory.proxyproto = self

    def onOpen(self):
        print(
            "{0}: backend WebSocket connection open.".format(
                self.factory.clientconnection.request.peer
            )
        )

    def onMessage(self, payload, isBinary):
        """
        If we get data from BACKEND forward it to our client connection, performing string replacement if requested
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

    import sys

    from twisted.python import log
    from twisted.internet import reactor

    load_dotenv()
    log.startLogging(sys.stdout)
    # txaio.start_logging(level="debug")

    factory = WebSocketServerFactory()
    factory.protocol = WebsocketInfoServerProtocol
    factory.setProtocolOptions(
        autoPingInterval=10, autoPingTimeout=3, trustXForwardedFor=1
    )

    reactor.listenTCP(os.environ.get("PORT", 8080), factory)
    reactor.run()
