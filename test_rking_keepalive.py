import unittest
from unittest.mock import patch
import rking_keepalive as rk

def pair(state, stat=None, uptime=0, **extra):
    return ({'id':55, 'state':state, **extra},{'ok':True,'state':state if stat is None else stat, 'uptime_seconds':uptime})

class Fake:
    def __init__(self, values, fail=False): self.values=list(values);self.starts=0;self.fail=fail
    def snapshot(self): return self.values.pop(0) if len(self.values)>1 else self.values[0]
    def start(self):
        self.starts+=1
        if self.fail: raise TimeoutError()
        return 200, {'ok':True}

class Tests(unittest.TestCase):
    @patch('rking_keepalive.time.sleep')
    def test_online_no_action(self, sleep):
        c=Fake([pair('online',uptime=99)]);self.assertTrue(rk.maintain(c,2));self.assertEqual(c.starts,0)
    @patch('rking_keepalive.time.sleep')
    def test_offline_one_start_then_online(self,sleep):
        c=Fake([pair('offline'),pair('starting'),pair('online',uptime=1)]);self.assertTrue(rk.maintain(c,3));self.assertEqual(c.starts,1)
    @patch('rking_keepalive.time.sleep')
    def test_starting_never_running_is_failure(self,sleep):
        c=Fake([pair('starting')]);self.assertFalse(rk.maintain(c,3));self.assertEqual(c.starts,0)
    @patch('rking_keepalive.time.sleep')
    def test_disagreement_no_start(self,sleep):
        c=Fake([pair('offline','online')]);self.assertFalse(rk.maintain(c,2));self.assertEqual(c.starts,0)
    @patch('rking_keepalive.time.sleep')
    def test_http_success_not_enough(self,sleep):
        c=Fake([pair('offline')]);self.assertFalse(rk.maintain(c,3));self.assertEqual(c.starts,1)
    @patch('rking_keepalive.time.sleep')
    def test_timed_out_start_not_repeated(self,sleep):
        c=Fake([pair('offline')],True);self.assertFalse(rk.maintain(c,3));self.assertEqual(c.starts,1)
    @patch('rking_keepalive.time.sleep')
    def test_expired_still_attempts(self,sleep):
        c=Fake([pair('offline',expired=True)]);self.assertFalse(rk.maintain(c,1));self.assertEqual(c.starts,1)
    @patch('rking_keepalive.time.sleep')
    def test_disk_full_no_start(self,sleep):
        c=Fake([pair('offline',disk_over=True)]);self.assertFalse(rk.maintain(c,3));self.assertEqual(c.starts,0)
    @patch('rking_keepalive.time.sleep')
    def test_no_uptime_no_success(self,sleep):
        c=Fake([pair('online',uptime=0)]);self.assertFalse(rk.maintain(c,2));self.assertEqual(c.starts,0)

if __name__ == '__main__': unittest.main()
