from places2leads import validate as v
from places2leads.enrich import emails_in


def test_clean_email_accepts_real_and_rejects_junk():
    assert v.clean_email("Info@CoolAir.com ") == "info@coolair.com"
    assert v.clean_email("mailto:sales@acme.co?subject=hi") == "sales@acme.co"
    for bad in ["logo@2x.png", "user@domain.com", "noreply@acme.com", "abc@example.com",
                "careers@acme.com", "not-an-email", None]:
        assert v.clean_email(bad) is None


def test_matches_website():
    assert v.matches_website("info@coolair.com", "https://www.coolair.com/contact")
    assert v.matches_website("a@mail.coolair.com", "coolair.com")
    assert not v.matches_website("coolair@gmail.com", "coolair.com")


def test_drop_chains_and_dedupe():
    recs = [{"email": f"loc{i}@bigchain.com"} for i in range(8)] + \
           [{"email": "owner@small.com"}, {"email": "owner@small.com"}, {"email": "me@gmail.com"}]
    out = v.dedupe(v.drop_chains(recs, max_per_domain=5))
    assert [r["email"] for r in out] == ["owner@small.com", "me@gmail.com"]


def test_emails_in_handles_obfuscation():
    html = 'Call us or write to info [at] coolair.com or <a href="mailto:jo%40coolair.com">Jo</a>'
    found = emails_in(html.replace(" [at] ", "[at]"))
    assert "info@coolair.com" in found and "jo@coolair.com" in found
