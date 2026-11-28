import unittest
from datetime import datetime, timedelta, timezone
from coalbyte_probe import decision
NOW=datetime(2026,11,28,tzinfo=timezone.utc)
EMAIL='test@example.test'

def row(**updates):
 d={'user_email':EMAIL,'status':'active','expires_at':(NOW+timedelta(hours=1)).isoformat()};d.update(updates);return d

class GuardTests(unittest.TestCase):
 def test_in_window(self): self.assertEqual(decision(row(),EMAIL,NOW),'IN_WINDOW')
 def test_expired_active(self): self.assertEqual(decision(row(expires_at=(NOW-timedelta(hours=1)).isoformat()),EMAIL,NOW),'IN_WINDOW')
 def test_over_48(self): self.assertEqual(decision(row(expires_at=(NOW+timedelta(hours=48,seconds=1)).isoformat()),EMAIL,NOW),'TOO_EARLY')
 def test_at_48(self): self.assertEqual(decision(row(expires_at=(NOW+timedelta(hours=48)).isoformat()),EMAIL,NOW),'IN_WINDOW')
 def test_suspended(self): self.assertEqual(decision(row(status='suspended'),EMAIL,NOW),'NOT_ACTIVE')
 def test_missing_email(self): self.assertEqual(decision(row(user_email=None),EMAIL,NOW),'EMAIL_MISMATCH_OR_MISSING')
 def test_missing_expiry(self): self.assertEqual(decision(row(expires_at=''),EMAIL,NOW),'EXPIRY_UNKNOWN')
 def test_timezone_required(self): self.assertEqual(decision(row(expires_at='2026-11-28T12:00:00'),EMAIL,NOW),'EXPIRY_UNKNOWN')

if __name__=='__main__': unittest.main()
