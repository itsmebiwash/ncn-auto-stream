from wc_scores import generate_score_html
from html2image import Html2Image
import os

hti = Html2Image(size=(1080, 1080))
hti.output_path = '.'

# Sample 1: FINISHED match
html1 = generate_score_html("Colombia", "Ghana", 1, 0, "FINISHED", None, "Quarter Final")
hti.screenshot(html_str=html1, save_as='sample_ft.png')
print("sample_ft.png saved!")

# Sample 2: LIVE match
html2 = generate_score_html("Argentina", "Egypt", 2, 1, "IN_PLAY", 67, "Semi Final")
hti.screenshot(html_str=html2, save_as='sample_live.png')
print("sample_live.png saved!")

# Sample 3: Upcoming
html3 = generate_score_html("Portugal", "Spain", None, None, "TIMED", None, "Quarter Final")
hti.screenshot(html_str=html3, save_as='sample_upcoming.png')
print("sample_upcoming.png saved!")
