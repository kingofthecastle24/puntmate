import unittest,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from copy_validator import validate_post,validate_text,CopyValidationError
class CaptionSendGateTests(unittest.TestCase):
 def test_legacy_frozen_colorado_rejected(self):
  d=Path(__file__).resolve().parents[1]/'data/review/2026-11-06_Colorado_Avalanche_vs_Nashville_Predators'
  with self.assertRaises(CopyValidationError):validate_post(json.loads((d/'post-metadata.json').read_text()),(d/'telegram-post.txt').read_text(),(d/'instagram-caption.txt').read_text())
 def test_certainty_blocked_without_metadata(self):
  with self.assertRaises(CopyValidationError):validate_text('As close to a sure thing as sport gets.')
 def test_neutral_notice_passes(self):validate_text('This was the published pre-match selection, not a guaranteed result. The earlier certainty and unsupported squad-strength and pricing claims have been removed.')
 def test_publisher_revalidates_loaded_copy(self):
  s=(Path(__file__).resolve().parents[1]/'scripts/publish_pick.py').read_text();self.assertIn('validate_post(metadata, telegram_text, instagram_caption)',s)
