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
        print("Client connecting: {0}".format(request))
        if request.path == "/":
            # this might be a valid request, so we'll start a BACKEND connection
            print(
                "starting proxy backend connection attempt: {0}".format(
                    os.environ.get("BACKEND")
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
                privatecert = ssl.PrivateCertificate.fromCertificateAndKeyPair(
                    cert, key
                )
                print("loaded client cert {0}".format(privatecert))
                if os.environ.get("SSL_CLIENT_CA", False):
                    cacerts = ssl.Certificate.loadPEM(os.environ.get("SSL_CLIENT_CA"))
                    print("verifying CA cert {0}".format(cacerts))
                    sslfactory = privatecert.options(cacerts)
                else:
                    sslfactory = privatecert.options()
            connectWS(self.proxyfactory, contextFactory=sslfactory)

    def onOpen(self):
        """
        When the websocket connection open
        """
        print("Client WebSocket connection open.")

    def onMessage(self, payload, isBinary):
        """
        when the client sends data forward to BACKEND
        """

        if isBinary:
            print("Client Binary message received: {0} bytes".format(len(payload)))
        else:
            print("Client Text message received: {0}".format(payload.decode("utf8")))
        self.proxyfactory.proxyproto.sendMessage(payload)

    def onClose(self, wasClean, code, reason):
        """
        When the client closes the connection also close the BACKEND
        """
        print("Client connection closed with reason: {0}".format(reason))
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
        print("Proxy connecting: {0}".format(request.peer))
        self.factory.proxyproto = self

    def onOpen(self):
        print("Proxy WebSocket connection open.")

    def onMessage(self, payload, isBinary):
        """
        If we get data from BACKEND forward it to our client connection, performing string replacement if requested
        """

        if isBinary:
            print("Proxy Binary message received: {0} bytes".format(len(payload)))
        else:
            print("Proxy Text message received: {0}".format(payload.decode("utf8")))
        message = payload.decode("utf8")
        message = message.replace(
            os.environ.get("OLD_HOST", ""), os.environ.get("NEW_HOST", "")
        )
        self.factory.clientconnection.sendMessage(message.encode("utf8"))

    def onClose(self, wasClean, code, reason):
        """
        If the BACKEND connection gets closed also close the client connection
        """
        print("Proxy WebSocket connection closed: {0}".format(reason))
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
    factory.setProtocolOptions(autoPingInterval=10, autoPingTimeout=3)

    reactor.listenTCP(os.environ.get("PORT", 8080), factory)
    reactor.run()
