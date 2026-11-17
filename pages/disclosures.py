import dash

from Services.disclosures import disclosures

dash.register_page(__name__, path="/disclosures", name="Disclosures", title="Disclosures", order=99)

layout = disclosures
