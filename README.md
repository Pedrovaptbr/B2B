# 🚀 Protótipo B2R (Business to Revendedor)

## 🎯 Visão Geral (O que faz)

O **Protótipo B2R** é uma aplicação web de prospecção e geração de leads que valida um modelo de negócios **Pay-as-you-go** para revendedores.

Ele utiliza a Google Maps Platform para encontrar empresas segmentadas e permite que os usuários consumam créditos virtuais (mockados) para visualizar dados de contato (telefone, endereço).

## 🔒 Objetivo Principal: Integridade Financeira

O foco técnico desta versão (v1.6) é provar a segurança e a integridade do sistema de crédito.

O consumo de créditos é garantido pelo uso de **Transações Atômicas** do Google Firestore (RF009), que impede concorrência de escrita e garante que o saldo seja sempre debitado de forma segura e auditável.

## ✨ Recursos Chave

| Módulo | Descrição |
 | ----- | ----- |
| **Geração de Leads** | Busca de empresas com filtros avançados (Categoria, Localização, Raio) usando a Google Maps Platform (RF001). |
| **Consumo de Créditos** | Débito de 5 Créditos para Busca e 1 Crédito para Visualização do Contato. O sistema inicia o saldo com **1000 Créditos** para testes (RF007). |
| **Gestão de Leads** | Salvamento e gerenciamento dos contatos adquiridos, com histórico de transações (RF010). |

## 🏗️ Arquitetura e Tecnologias

* **Banco de Dados:** Google Firebase Firestore (Gerenciamento de Saldo e Logs Atômicos).

* **Autenticação:** Firebase Auth (RNF004).

* **Prospecção:** Google Maps Platform API (Places API).

* **Frontend:** HTML/React/Angular (Decisão a ser tomada na implementação).

## ⚙️ Como Iniciar

1. **Autenticação:** O sistema utiliza o token de autenticação fornecido pelo ambiente (`__initial_auth_token`) ou faz login anonimamente.

2. **Inicialização de Saldo:** Na primeira execução, o saldo do usuário é automaticamente definido para `1000.0 Créditos` (RF007 - MOCK) para permitir os testes.

**Nota:** Os detalhes completos do fluxo de trabalho e especificações técnicas (DSE) podem ser encontrados no arquivo `STRUCTURE.md`.