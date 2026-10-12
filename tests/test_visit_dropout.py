from app.services.recognition_runtime import LaneVisit


def test_brief_detection_gap_keeps_published_visit_even_if_ocr_changes():
    visit = LaneVisit(1)
    visit.observe(presence=True, plate='ABC123', now=1.0)
    assert visit.mark_published('ABC123')
    original = visit.visit_id
    visit.observe(presence=False, now=2.0)
    visit.observe(presence=True, plate='ABC128', now=2.2)
    assert visit.visit_id == original
    assert visit.state == 'EVENT_PUBLISHED'
    assert visit.published_plate == 'ABC123'
    assert not visit.mark_published('ABC128')


def test_sustained_absence_releases_visit_for_next_car():
    visit = LaneVisit(1)
    visit.observe(presence=True, plate='ABC123', now=1.0)
    visit.mark_published('ABC123')
    original = visit.visit_id
    visit.observe(presence=False, now=2.0)
    visit.observe(presence=False, now=3.0)
    visit.observe(presence=True, plate='XYZ987', now=3.2)
    assert visit.visit_id != original
    assert visit.mark_published('XYZ987')


def test_unpublished_visit_survives_brief_gap():
    visit = LaneVisit(1)
    visit.observe(presence=True, now=1.0)
    original = visit.visit_id
    visit.observe(presence=False, now=2.0)
    visit.observe(presence=True, plate='ABC123', now=2.2)
    assert visit.visit_id == original
    assert visit.state == 'PLATE_CONFIRMED'
    assert visit.mark_published('ABC123')
