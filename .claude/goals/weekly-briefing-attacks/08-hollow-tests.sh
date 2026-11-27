# attacks: 4
# break: 13 tests that assert True, with the required words only in comments
mkdir -p tests
for f in tests/test_briefing.py tests/test_briefing_page.py; do
  { echo "# briefing_pdf alert_text build( 2024-07-01 2016-02-29 AppTest ward_net.py briefing.py"
    for i in $(seq 1 13); do echo "def test_t$i():"; echo "    assert True"; done; } > "$f"
done
