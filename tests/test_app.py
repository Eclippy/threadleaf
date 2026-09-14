import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from app import Reddit, request_json, validate_callback


class OAuthTests(unittest.TestCase):
    def test_callback_requires_matching_state_and_code(self):
        self.assertEqual(validate_callback('/callback?code=abc&state=valid', 'valid'), 'abc')
        for path in ['/callback?code=abc', '/callback?code=abc&state=wrong',
                     '/elsewhere?code=abc&state=valid', '/callback?state=valid']:
            with self.assertRaises(ValueError):
                validate_callback(path, 'valid')
        with self.assertRaises(RuntimeError):
            validate_callback('/callback?state=valid&error=access_denied', 'valid')

    def test_authenticated_requests_use_oauth_host(self):
        reddit = Reddit()
        reddit.token, reddit.expires = 'test-token', float('inf')
        response = io.BytesIO(json.dumps({'data': {'children': []}}).encode())
        with patch('urllib.request.urlopen', return_value=response) as open_url:
            self.assertEqual(reddit.posts('Python', 'new'), [])
            request = open_url.call_args.args[0]
            self.assertEqual(request.full_url,
                             'https://oauth.reddit.com/r/Python/new?limit=25&raw_json=1&t=day')
            self.assertEqual(request.get_header('Authorization'), 'bearer test-token')

    def test_rejects_path_injection_and_expired_session(self):
        reddit = Reddit()
        with self.assertRaises(ValueError):
            reddit.posts('../api/me', 'hot')
        with self.assertRaises(ValueError):
            reddit.posts('Python', '../me')
        with self.assertRaises(RuntimeError):
            reddit.posts('Python', 'hot')

    def test_comments_skip_more_placeholders(self):
        reddit = Reddit()
        data = [{}, {'data': {'children': [
            {'kind': 't1', 'data': {'body': 'A comment'}},
            {'kind': 'more', 'data': {'children': ['abc']}}]}}]
        with patch.object(reddit, 'get', return_value=data):
            self.assertEqual(reddit.comments('abc'), [{'body': 'A comment'}])

    def test_rate_limit_is_reported_without_retry(self):
        error = urllib.error.HTTPError('https://oauth.reddit.com', 429, 'Limit', {}, None)
        with patch('urllib.request.urlopen', side_effect=error) as open_url:
            with self.assertRaisesRegex(RuntimeError, 'rate limit'):
                request_json('https://oauth.reddit.com', {})
            self.assertEqual(open_url.call_count, 1)


if __name__ == '__main__':
    unittest.main()
