# Websocket proxy with string replacing

* Configured with environment variables, at least BACKEND needs to be set with a ws:// or wss:// URL
* This application is a Websocket server providing an websocket endpoint listening on PORT (8080 by default)
* the client request path is ignored, so /foobar will also get proxied to the same BACKEND URL
* GET request parameters from the client are appended to the BACKEND URL
* all websocket messages/queries are forwarded to BACKEND and vice versa
* all messages from BACKEND will be forwarded to the client
* to use ssl-client-certificates with BACKEND put them in SSL_CLIENT_CERT/SSL_CLIENT_KEY env variables
* Verification for the CA-certificate in SSL_CLIENT_CA is implemented but untested
* (all certs/keys in PEM format starting with "-----BEGIN..." includinig newlines)
* on the answer of BACKEND string replacement can be performed: all occurrences of OLD_HOST strings are replaced with NEW_HOST

