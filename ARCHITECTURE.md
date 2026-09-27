from __future__ import annotations

from io import BytesIO

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def render_cv_pdf(profile: dict, offer: dict, strategy) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=(595, 842), rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(profile.get('candidate_name', 'Candidate'), styles['Title']))
    story.append(Paragraph(f"{profile.get('city', '')} — {offer.get('job_title', 'poste cible')} — {offer.get('company', '')}", styles['BodyText']))
    story.append(Spacer(1, 18))
    story.append(Paragraph("Positionnement", styles['Heading2']))
    story.append(Paragraph(strategy.positioning, styles['BodyText']))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Compétences clés", styles['Heading2']))
    story.append(Paragraph(", ".join(profile.get('skills', [])[:10]), styles['BodyText']))
    story.append(Spacer(1, 12))

    for exp in profile.get('experiences', [])[:3]:
        story.append(Paragraph(f"{exp['title']} — {exp['company']} ({exp['period']})", styles['Heading3']))
        story.append(Paragraph(exp['summary'], styles['BodyText']))
        for result in exp.get('results', [])[:3]:
            story.append(Paragraph(f"• {result}", styles['BodyText']))
        story.append(Spacer(1, 10))

    doc.build(story)
    return buffer.getvalue()


def render_letter_pdf(profile: dict, offer: dict, strategy) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=(595, 842), rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(profile.get('candidate_name', 'Candidate'), styles['Title']))
    story.append(Paragraph(f"{profile.get('city', '')} | {profile.get('email', '')}", styles['BodyText']))
    story.append(Spacer(1, 18))
    story.append(Paragraph(f"Objet : Candidature au poste de {offer.get('job_title', 'poste')} chez {offer.get('company', '')}", styles['BodyText']))
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "Bonjour,\n\n"
        "Je souhaite candidater pour le poste de " + (offer.get('job_title') or 'poste') + " au sein de " + (offer.get('company') or 'votre entreprise') + ". "
        "Mon parcours mêle prospection commerciale, relation client et développement de portefeuille, ce qui correspond à la logique de ce poste. "
        "J'ai su créer de la valeur sur des missions exigeant de la rigueur, de la proximité client, de la négociation et de la transformation des opportunités en résultats concrets.\n\n"
        "Je serais ravi de pouvoir apporter ce même niveau d'engagement sur ce poste, en m'appuyant sur ma capacité à structurer une approche commerciale claire, gérer efficacement des interactions clients et encoder de la valeur à travers des résultats mesurables.",
        styles['BodyText']
    ))
    story.append(Spacer(1, 20))
    story.append(Paragraph("Cordialement,", styles['BodyText']))
    doc.build(story)
    return buffer.getvalue()
