import requests

# Suas credenciais
GOOGLE_API_KEY = "AIzaSyDJqZUB9jXfNbF6SpIUQ2MQebCFdUsfI-s"


def extrair_leads_puros(nicho, localizacao):
    """Extrai nome, telefone e site do Google Maps."""

    # 1. Busca os IDs das empresas
    search_url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={nicho}+em+{localizacao}&key={GOOGLE_API_KEY}"
    response = requests.get(search_url).json()
    estabelecimentos = response.get('results', [])

    lista_final = []

    print(f"🔎 Buscando {nicho} em {localizacao}...")

    for local in estabelecimentos:
        place_id = local['place_id']

        # 2. Busca os detalhes específicos de cada ID (Telefone e Site)
        details_url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields=name,formatted_phone_number,website&key={GOOGLE_API_KEY}"
        detalhes = requests.get(details_url).json().get('result', {})

        # Organiza os dados
        lead = {
            "nome": detalhes.get('name'),
            "telefone": detalhes.get('formatted_phone_number', 'Não encontrado'),
            "site": detalhes.get('website', 'Não possui site')
        }

        lista_final.append(lead)
        print(f"✅ Extraído: {lead['nome']} | Tel: {lead['telefone']}")

    return lista_final


# --- EXECUÇÃO DIRETA ---
leads = extrair_leads_puros("Mecânicas", "Santo Amaro da Imperatriz")

print(f"\n🚀 Extração finalizada! {len(leads)} leads encontrados.")