"""
Websocket proxy with string replacement

Websocket server providing an websocket endpoint at /
all websocket messages are forwarded to Websocket endpoint BACKEND
The connection to BACKEND can be authenticated using SSL_CLIENT_CERT/SSL_CLIENT_KEY
Verification for the CA-certificate in SSL_CLIENT_CA is implemented but untested
on the answer of BACKEND string replacement can be performed: all occurrences
of OLD_HOST strings are replaced with NEW_HOST
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
    proxyfactory = None

    def onConnect(self, request):
        print("Client connecting: {0}".format(request.peer))

    def onOpen(self):
        print("Client WebSocket connection open.")
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
            privatecert = ssl.PrivateCertificate.fromCertificateAndKeyPair(cert, key)
            print("loaded client cert {0}".format(privatecert))
            if os.environ.get("SSL_CLIENT_CA", False):
                cacerts = ssl.Certificate.loadPEM(os.environ.get("SSL_CLIENT_CA"))
                print("verifying CA cert {0}".format(cacerts))
                sslfactory = privatecert.options(cacerts)
            else:
                sslfactory = privatecert.options()
        connectWS(self.proxyfactory, contextFactory=sslfactory)

    def onMessage(self, payload, isBinary):
        if isBinary:
            print("Client Binary message received: {0} bytes".format(len(payload)))
        else:
            print("Client Text message received: {0}".format(payload.decode("utf8")))
        self.proxyfactory.proxyproto.sendMessage(payload)

    def onClose(self, wasClean, code, reason):
        print("Client WebSocket connection closed: {0}".format(reason))
        if self.proxyfactory is not None:
            self.proxyfactory.proxyproto.sendClose()


class WebsocketInfoProxyProtocol(WebSocketClientProtocol):
    def onConnect(self, request):
        print("Proxy connecting: {0}".format(request.peer))
        self.factory.proxyproto = self

    def onOpen(self):
        print("Proxy WebSocket connection open.")

    def onMessage(self, payload, isBinary):
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
        print("Proxy WebSocket connection closed: {0}".format(reason))
        self.factory.clientconnection.sendClose()


if __name__ == "__main__":

    import sys

    from twisted.python import log
    from twisted.internet import reactor

    load_dotenv()
    # log.startLogging(sys.stdout)
    txaio.start_logging(level="debug")

    factory = WebSocketServerFactory()
    factory.protocol = WebsocketInfoServerProtocol
    factory.setProtocolOptions(autoPingInterval=10, autoPingTimeout=3)

    reactor.listenTCP(8080, factory)
    reactor.run()
