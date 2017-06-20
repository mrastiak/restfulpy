
import unittest
import time

from nanohttp import json, Controller, context, settings

from restfulpy.authentication import Authenticator
from restfulpy.authorization import authorize
from restfulpy.principal import JwtPrincipal, JwtRefreshToken
from restfulpy.testing import WebAppTestCase, As
from restfulpy.tests.helpers import MockupApplication


class MockupMember:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class MockupStatelessAuthenticator(Authenticator):
    def validate_credentials(self, credentials):
        email, password = credentials
        if password == 'test':
            return MockupMember(id=1, email=email, roles=['admin', 'test'])
        return None

    def create_refresh_principal(self, member_id=None):
        return JwtRefreshToken(dict(
            id=member_id
        ))

    def create_principal(self, member_id=None, session_id=None):
        return JwtPrincipal(dict(id=1, email='test@example.com', roles=['admin', 'test'], sessionId='1'))


class Root(Controller):

    @json
    def index(self):
        return context.form

    @json
    def login(self):
        principal = context.application.__authenticator__.login((context.form['email'], context.form['password']))
        return dict(token=principal.dump())

    @json
    @authorize
    def me(self):
        return context.identity.payload


class AuthenticatorTestCase(WebAppTestCase):
    application = MockupApplication('MockupApplication', Root(), authenticator=MockupStatelessAuthenticator())

    @classmethod
    def configure_app(cls):
        cls.application.configure(force=True)
        settings.merge("""
            jwt:
              max_age: .3
              refresh_token:
                max_age: 3
        """)

    def test_login(self):
        response, headers = self.request('ALL', 'GET', '/login', json=dict(email='test@example.com', password='test'))
        self.assertIn('token', response)
        self.assertEqual(headers['X-Identity'], '1')

        self.wsgi_app.jwt_token = response['token']
        response, headers = self.request('ALL', 'GET', '/', json=dict(a='a', b='b'))
        self.assertEqual(headers['X-Identity'], '1')

    def test_refresh_token(self):
        response, headers = self.request('ALL', 'GET', '/login', json=dict(email='test@example.com', password='test'))
        refresh_token = headers['Set-Cookie'].split('; ')[0]
        self.assertIn('token', response)
        self.assertTrue(refresh_token.startswith('refresh-token='))

        # Login on client
        token = response['token']
        self.wsgi_app.jwt_token = token

        # Request a protected resource after the token has been expired expired, without the cookies
        time.sleep(1)
        self.request(As.member, 'GET', '/me', expected_status=401)

        # Request a protected resource after the token has been expired expired, with appropriate cookies.
        response, response_headers = self.request(
            As.member, 'GET', '/me',
            headers={
                'Cookie': refresh_token
            }
        )
        self.assertIn('X-New-JWT-Token', response_headers)
        self.assertIsNotNone(response_headers['X-New-JWT-Token'])

        # Test with invalid Refresh Token
        self.request(
            As.member, 'GET', '/me',
            headers={
                'Cookie': 'refresh-token=InvalidToken'
            },
            expected_status=400
        )


if __name__ == '__main__':
    unittest.main()
