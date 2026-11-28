import unittest
from unittest.mock import patch
from datetime import datetime,timezone,timedelta
import coalbyte_renew as m
NOW=datetime(2026,11,28,tzinfo=timezone.utc)
EMAIL='a@example.test'

def data(hours=5):
 exp=(NOW+timedelta(hours=hours)).isoformat();return {'status':'active','user_email':EMAIL,'expires_at':exp},{'status':'active','expiresAt':exp}

class Tests(unittest.TestCase):
 def test_due_bot(self):
  a,b=data();self.assertEqual(m.can_write(m.BOT_ID,a,EMAIL,NOW,b),'READY')
 def test_too_early(self):
  a,b=data(49);self.assertEqual(m.can_write(m.BOT_ID,a,EMAIL,NOW,b),'TOO_EARLY')
 def test_inconsistent_expiry(self):
  a,b=data();b['expiresAt']=(NOW+timedelta(hours=4)).isoformat();self.assertEqual(m.can_write(m.BOT_ID,a,EMAIL,NOW,b),'PUBLIC_STATUS_MISMATCH')
 def test_no_mc_duration_guess(self):
  a,b=data();self.assertEqual(m.can_write('c3f65fbb',a,EMAIL,NOW,b),'PLAN_DURATION_UNCONFIRMED')
 def test_missing_email(self):
  a,b=data();a['user_email']=None;self.assertEqual(m.can_write('c3f65fbb',a,EMAIL,NOW,b),'EMAIL_MISMATCH_OR_MISSING')
 def test_expiry_unchanged_never_success(self):
  a,b=data()
  with patch.object(m,'read_row',side_effect=[a,a]),patch.object(m,'public_renewal',side_effect=[b,b]),patch.object(m,'patch_row',return_value=NOW+timedelta(days=5)):
   self.assertFalse(m.renew_one('https://example.test','key',m.BOT_ID,EMAIL,NOW))
 def test_update_verified_both_sources(self):
  a,b=data();new=NOW+timedelta(days=5);a2=dict(a,expires_at=new.isoformat());b2=dict(b,expiresAt=new.isoformat())
  with patch.object(m,'read_row',side_effect=[a,a2]),patch.object(m,'public_renewal',side_effect=[b,b2]),patch.object(m,'patch_row',return_value=new):self.assertTrue(m.renew_one('https://example.test','key',m.BOT_ID,EMAIL,NOW))
 def test_failed_patch_not_retried(self):
  a,b=data()
  with patch.object(m,'read_row',return_value=a),patch.object(m,'public_renewal',return_value=b),patch.object(m,'patch_row',side_effect=TimeoutError) as f:
   self.assertFalse(m.renew_one('https://example.test','key',m.BOT_ID,EMAIL,NOW));f.assert_called_once()
 def test_toearly_does_not_patch(self):
  a,b=data(49)
  with patch.object(m,'read_row',return_value=a),patch.object(m,'public_renewal',return_value=b),patch.object(m,'patch_row') as f:
   self.assertTrue(m.renew_one('https://example.test','key',m.BOT_ID,EMAIL,NOW));f.assert_not_called()
 def test_running_no_start(self):
  with patch.object(m,'real_state',return_value='running'),patch('urllib.request.urlopen') as f:
   self.assertTrue(m.ensure_running(m.BOT_ID));f.assert_not_called()
 def test_unknown_does_not_guess_start(self):
  with patch.object(m,'real_state',side_effect=TimeoutError),patch('urllib.request.urlopen') as f:
   self.assertFalse(m.ensure_running(m.BOT_ID));f.assert_not_called()
if __name__=='__main__':unittest.main()
