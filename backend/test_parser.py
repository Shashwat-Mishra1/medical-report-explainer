from parser import parse_report

sample = """Test
Result
Unit
Reference Range
Hemoglobin
10.2
g/dL
12.0–16.0
WBC Count
7,800
/µL
4,000–11,000
RBC Count
4.1
million/µL
3.8–5.2
Platelet Count
250,000
/µL
150,000–450,000
Fasting Glucose
108
mg/dL
70–99
Total Cholesterol
185
mg/dL
<200
Hb 9.8 g/dL 12.0 - 15.5"""

for t in parse_report(sample):
    print(t["test"], t["value"], t["unit"], t["ref_low"], t["ref_high"], "->", t["status"])