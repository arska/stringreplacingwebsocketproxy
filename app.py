"""
Websocket proxy with string replacement

Websocket server providing an websocket endpoint at /
all websocket messages are forwarded to Websocket endpoint BACKEND
on the answer of BACKEND string replacement is performed: all occurrences
of OLD_HOST strings are replaced with NEW_HOST
"""
from autobahn.twisted.websocket import WebSocketServerProtocol, WebSocketServerFactory
from autobahn.twisted.websocket import WebSocketClientProtocol, WebSocketClientFactory
from autobahn.twisted.websocket import connectWS
import time
import txaio
from dotenv import load_dotenv
import os


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
        self.proxyfactory.setProtocolOptions(autoPingInterval=5, autoPingTimeout=2)
        self.proxyfactory.protocol = WebsocketInfoProxyProtocol
        self.proxyfactory.clientconnection = self
        connectWS(self.proxyfactory)

    def onMessage(self, payload, isBinary):
        if isBinary:
            print("Client Binary message received: {0} bytes".format(len(payload)))
        else:
            print("Client Text message received: {0}".format(payload.decode("utf8")))
        self.proxyfactory.proxyproto.sendMessage(payload)

    def onClose(self, wasClean, code, reason):
        print("Client WebSocket connection closed: {0}".format(reason))
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
            os.environ.get("OLD_HOST"), os.environ.get("NEW_HOST")
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

    factory = WebSocketServerFactory(u"ws://127.0.0.1:8080")
    factory.protocol = WebsocketInfoServerProtocol

    reactor.listenTCP(8080, factory)
    reactor.run()
