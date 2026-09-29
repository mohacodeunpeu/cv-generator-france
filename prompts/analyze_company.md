<!-- prompt: analyze_company | version: 2 -->
Tu résumes ce que l'on SAIT de l'entreprise « {{company}} » à partir des seules sources fournies (texte de l'offre et sources enregistrées avec URL et date). Tu n'as pas accès au web et tu n'utilises pas tes connaissances générales.

TEXTE DE L'OFFRE :
"""
{{offer_text}}
"""
SOURCES ENREGISTRÉES (peut être vide) :
{{sources}}

Réponds UNIQUEMENT par ce JSON :
{
  "activity": "…", "products": ["…"], "positioning": "…", "vocabulary": ["…"],
  "facts": [{"text": "…", "source": "offer|<url>", "quote": "citation exacte"}],
  "unknown": ["ce qu'il faudrait vérifier sur le site officiel"]
}
Chaque élément de `facts` cite sa source et une citation exacte. Rien d'autre.
