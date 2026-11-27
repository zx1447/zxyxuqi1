import io
import socket
import unittest
import urllib.error
from unittest.mock import patch
import checkin_blackflame as b

START='00ae45aaaace23d4db327c16de0332eec03d185178'
CANCEL='00dcf4d6d794b7094770bcf657415f31a94aed85a7'
VERIFY='0038f3e3a2232822f7add9e9001acbeea64021076c'
JS=f'(0,s.createServerReference)("{START}",s.callServer,void 0,s.findSourceMapURL,"startAdWatch"),(0,s.createServerReference)("{CANCEL}",s.callServer,void 0,s.findSourceMapURL,"cancelAdWatch"),(0,s.createServerReference)("{VERIFY}",s.callServer,void 0,s.findSourceMapURL,"verifyAndRewardAdWatch")'

class Tests(unittest.TestCase):
 def test_current_42_character_action_ids(self):
  self.assertEqual(b.parse_action_ids(JS),{'startAdWatch':START,'cancelAdWatch':CANCEL,'verifyAndRewardAdWatch':VERIFY})
 def test_conflicting_action_ids_rejected(self):
  with self.assertRaises(RuntimeError): b.parse_action_ids(JS+JS.replace(START,'a'*42))
 def test_discover_requires_start_and_verify(self):
  with patch.object(b,'site',return_value=(200,'<script src="/_next/static/chunks/x.js"></script>')),patch.object(b,'req',return_value=(200,JS)):
   b.rediscover_ids();self.assertEqual((b.ACT_START,b.ACT_VERIFY),(START,VERIFY))
  with patch.object(b,'site',return_value=(200,'<script src="/_next/static/chunks/x.js"></script>')),patch.object(b,'req',return_value=(200,JS.split(',l=')[0] if ',l=' in JS else 'no refs')):
   with self.assertRaises(RuntimeError): b.rediscover_ids()
 def test_flight_success_and_error(self):
  objs=b.flight_objects('0:{"x":1}\n1:{"success":true,"requiredSeconds":30}\n');self.assertEqual(b.find_success(objs)['requiredSeconds'],30);self.assertEqual(b.flight_error('1:{"error":"bad"}'),'bad')
 @patch('checkin_blackflame.time.sleep')
 def test_reward_requires_response_and_balance(self,sleep):
  with patch.object(b,'action',side_effect=[(200,'1:{"success":true,"requiredSeconds":30}'),(200,'1:{"success":true}')]),patch.object(b,'coins_now',side_effect=[100,101]):self.assertEqual(b.one_round(1),(True,1))
  with patch.object(b,'action',side_effect=[(200,'1:{"success":true,"requiredSeconds":30}'),(200,'1:{"success":true}')]),patch.object(b,'coins_now',side_effect=[100,100]):self.assertEqual(b.one_round(1),(False,0))
  with patch.object(b,'action',side_effect=[(200,'1:{"success":true,"requiredSeconds":30}'),(200,'1:{"foo":"bar"}')]),patch.object(b,'coins_now',side_effect=[100,101]):self.assertEqual(b.one_round(1),(False,0))
 @patch('checkin_blackflame.time.sleep')
 def test_404_start_never_verifies(self,sleep):
  with patch.object(b,'action',return_value=(404,'')) as act,patch.object(b,'coins_now',return_value=100):
   self.assertEqual(b.one_round(1),(False,0));act.assert_called_once()
 @patch('checkin_blackflame.time.sleep')
 def test_post_network_failure_no_retry(self,sleep):
  with patch.object(b.opener,'open',side_effect=socket.timeout('timed out')) as op:
   with self.assertRaises(socket.timeout):b.req('https://example.com',method='POST',retries=5)
   self.assertEqual(op.call_count,1)
 def test_http404_returned_not_retried(self):
  err=urllib.error.HTTPError('https://example.com',404,'Not found',{},io.BytesIO(b'Not found'))
  with patch.object(b.opener,'open',side_effect=err) as op:
   self.assertEqual(b.req('https://example.com',method='POST'),(404,'Not found'));self.assertEqual(op.call_count,1)
 def test_main_does_not_ignore_partial_failure(self):
  with patch.object(b,'TOKEN','present'),patch.object(b,'RUN_MINUTES',0),patch.object(b,'WATCHES',2),patch.object(b,'login'),patch.object(b,'rediscover_ids'),patch.object(b,'coins_now',side_effect=[100,101]),patch.object(b,'one_round',side_effect=[(True,1),(False,0)]):
   self.assertEqual(b.main(),2)
if __name__ == '__main__': unittest.main()
