import os
from html2image import Html2Image
from main import generate_html_card
hti = Html2Image(size=(1080, 1350))
bg_image_url = 'https://images.unsplash.com/photo-1585829365295-ab7cd400c167?w=1080&h=1350&fit=crop'
html_str = generate_html_card(
    'National Service Corps Bill Tabled in Parliament, Proposes Nepal Army Training for Students and All Citizens During National Emergencies',
    'Army Training for Students',
    'During National Crises',
    bg_image_url
)
hti.screenshot(html_str=html_str, save_as='sample_card_v2.png')
