# Plano de Desenvolvimento do Protótipo B2R (v1.6) - Especificação Detalhada

**Versão:** 1.6 - Consolidação e Detalhamento Máximo
**Foco Principal:** Validação do Módulo de Busca (Google API) e da Lógica de Consumo de Créditos (Mockado).
**Exclusões:** API de Mensagens (Z-API) e Gateway de Pagamento (Mercado Pago).

---

## 1. Resumo Executivo e Escopo

O Protótipo v1.6 destina-se a validar o ciclo de vida da prospecção por demanda. O foco é garantir a **integridade financeira** do modelo de Pay-as-you-go, mesmo utilizando créditos simulados (mockados) para testar a lógica central.

| Categoria | Detalhe |
| :--- | :--- |
| **Tecnologias Core** | Google Maps Platform API (RF001), Firebase/Firestore (RF008, RF009, RF010), Firebase/Google Auth (RNF004). |
| **Propósito Principal** | Provar a viabilidade técnica e financeira do débito atômico de créditos e a eficácia do RF002. |
| **Público Alvo** | Revendedores B2R (Business to Revendedor). |
| **Resultado Esperado** | Uma aplicação web funcional que gere leads segmentados e debite o saldo do Revendedor de forma segura, auditável e rastreável. |

---

## 2. Requisitos Funcionais e Não-Funcionais (DSE v1.6)

### Requisitos Funcionais (RF)

| ID | Requisito Funcional | Detalhamento e Critérios de Aceitação |
| :--- | :--- | :--- |
| **RF001** | **Integração com Google Business** | Utilizar `Places API` ou equivalente da Google Maps Platform. Consultas devem retornar: `place_id` (para uso como `leadId`), Nome, Telefone (`RF003`), Endereço (`RF003`), Localização (Lat/Lng) e Tipos/Categoria. |
| **RF002** | **Módulo de Prospecção Avançada** | Implementar interface com 3 filtros obrigatórios: **Categoria** (seleção pré-definida), **Localização** (campo de texto, auto-sugestão do Google) e **Raio** (seleção em Km: 5km, 10km, 20km). |
| **RF002.3** | **Lead Scoring Simples** | Atribuir um **Score (1 a 100)** para ordenação dos resultados. Lógica inicial: Atribuição de 50 pontos base + 50 pontos se a empresa possuir um `website` ou `rating > 4.0` (dados da Google API). |
| **RF003** | **Exibição do Contato** | Os campos `phone` e `address` devem ser exibidos **somente após** a conclusão da Transação Atômica de 1 Crédito (RF009) e o salvamento do lead (RF005). |
| **RF004 / RF005** | **Gestão e Salvamento de Contatos** | O salvamento do lead na coleção `leads` é um passo **OBRIGATÓRIO** da Transação Atômica de 1 Crédito. O `leadId` (Place ID) deve ser a chave de indexação para evitar duplicação na lista pessoal. |
| **RF006** | **Gestão de Status Simples** | Permitir que o Revendedor mude o status do lead manualmente. O ciclo de vida sugerido é: `Novo` (Padrão após RF005) -> `Contatado` -> `Interessado` -> `Fechado` ou `Perdido`. |
| **RF007 (MOCK)** | **Módulo de Compra (Mockado)** | Na inicialização do usuário, se o documento `user_data` não existir, criar o `currentBalance` fixado em **1000.0 Créditos**. |
| **RF009** | **Sistema de Consumo de Créditos** | Débito em tempo real usando Transações Atômicas do Firestore (detalhado na Seção 6.2). Custo: 5.0 Créditos (Busca) e 1.0 Crédito (Visualização Detalhada). |
| **RF010** | **Histórico de Transações** | A coleção `transactions` deve ser preenchida com metadados de cada débito, incluindo o saldo após a transação (`balanceAfter`), para fins de auditoria (RNF-P). |

### Requisitos Não-Funcionais (RNF)

| ID | Requisito Não-Funcional | Descrição Detalhada |
| :--- | :--- | :--- |
| **RNF004** | **Segurança e Autenticação** | Acesso **OBRIGATÓRIO** via Firebase Auth. Utilizar `__initial_auth_token` e, se ausente, `signInAnonymously()`. O `userId` (uid do Firebase) será o identificador primário. |
| **RNF-P** | **Precisão Financeira** | O campo `currentBalance` deve ser do tipo `Number` para garantir precisão e consistência. As Transações Atômicas (RF009) garantem a precisão. |
| **RNF-D** | **Design Responsivo** | Layout adaptável a desktops, tablets e mobile, com foco na usabilidade do mapa e da lista de leads. |

---

## 3. Modelo de Negócios e Logística Financeira

### Detalhamento de Lucro e Custos

O modelo é *Pay-as-you-go*, onde o preço do crédito (R$ 0,10) é estabelecido para garantir uma margem de lucro significativa sobre os custos variáveis da Google API.

| Ação | Custo em Créditos | Equivalente em R$ | Margem de Lucro (Exemplo - Bruta) |
| :--- | :--- | :--- | :--- |
| **Busca/Prospecção** | **5 Créditos** | R$ 0,50 | R$ 0,50 - (Custos API + Taxas Transação) ≈ **R$ 0,47** |
| **Visualização Detalhada** | **1 Crédito** | R$ 0,10 | R$ 0,10 - (Custos API + Taxas Transação) ≈ **R$ 0,08** |

### Logística de Pagamento (Modelo de Produção Futuro - v2.0)

1.  **Compra de Créditos:** O Revendedor paga ao seu **Gateway de Pagamento** (Mercado Pago).
2.  **Seu Recebimento:** O valor líquido (após taxas do Mercado Pago) é depositado na sua conta.
3.  **Pagamento da Google:** Sua empresa utiliza um **Cartão Digital Corporativo** para cobrir a fatura consolidada mensal da Google Maps Platform.
4.  **Geração de Lucro:** Seu lucro é realizado imediatamente no recebimento do Revendedor, pois o preço do crédito é ajustado para cobrir o custo da API e garantir a margem.

---

## 4. Estrutura UX/UI (Wireframes Detalhados)

A interface deve ser construída em um único arquivo HTML/React/Angular e ter uma navegação baseada em *state* (Dashboard vs. Prospecção).

### Dashboard (Tela 1) - `RF008, RF004, RNF004`
* **Header:** Nome do Usuário (RNF004) e **SALDO ATUAL DE CRÉDITOS** (Atualizado via `onSnapshot` do Firestore).
* **Corpo:** Cartões de Desempenho (Total de Leads Salvos, Total Contatados, Total Fechados), obtidos por consulta agregada/filtrada na coleção `leads`.
* **Ação Principal:** Botão `INICIAR NOVA PROSPECÇÃO`.
* **Visualização Secundária:** Tabela com Leads Recentes e opção de acessar o Histórico de Transações (RF010).

### Tela de Prospecção (Tela 2) - `RF002, RF003, RF009`
1.  **Formulário de Filtros:** Campos de entrada e *dropdowns* para os filtros (RF002).
2.  **Alerta de Custo:** Área de notificação exibindo: **Custo para GERAR LISTA DE LEADS: 5 Créditos**.
3.  **Ação de Busca:** Botão `GERAR LISTA DE LEADS` que **dispara a Transação Atômica de 5 Créditos**.
4.  **Resultados:** Lista de empresas com `Nome` e `Score (RF002.3)`.
5.  **Ação de Consumo de Lead:** Botão `VER CONTATO (1 CRÉDITO)`.
    * Ao ser clicado, dispara a **Transação Atômica de 1 Crédito** e, em caso de sucesso, o botão é substituído pelos dados (`phone`, `address`) e pelo *dropdown* de `Status` (RF006).

---

## 5. Arquitetura de Dados (Firestore Detalhada)

As permissões de segurança devem garantir que apenas o `userId` logado possa ler e escrever em sua respectiva subárvore.

### 5.1. Coleção: `user_data` (Documento Único por Usuário)
* **Caminho:** `/artifacts/{appId}/users/{userId}/data/user_data/{userId}`
* **`currentBalance`:** Tipo `Number` (preferencialmente, para precisão).

### 5.2. Coleção: `leads`
* **Caminho:** `/artifacts/{appId}/users/{userId}/data/leads/{leadId}`
* **`leadId`:** O `place_id` do Google.
* **`status`:** String. Deve ter um índice para buscas rápidas (ex: "Leads Contatados").

### 5.3. Coleção: `transactions` (Log de Auditoria)
* **Caminho:** `/artifacts/{appId}/users/{userId}/data/transactions/{transactionId}`
* **`amount`** : Number. Usar números negativos para débitos (Ex: -5.0).
* **`balanceAfter`:** O valor final do saldo após a transação. Crucial para re-auditoria do RF008.

---

## 6. Fluxo de Implementação Crítica

### 6.1. Autenticação e Inicialização de Saldo (RNF004, RF007 MOCK)

1.  **Login:** `await signInWithCustomToken(auth, __initial_auth_token);` (ou `signInAnonymously()`).
2.  **Inicialização:** Chamar a função `initializeUserBalance(userId)` que executa um `getDoc` em `user_data`.
3.  **Criação do Saldo:** Se o documento não existir, usar `setDoc` para criar o documento com `currentBalance: 1000.0` e, em seguida, registrar a transação `CREDIT_MOCK_INIT` na coleção `transactions`.

### 6.2. Lógica Atômica de Consumo (RF009)

Esta operação é a mais crítica e deve ser executada exclusivamente via `runTransaction` do Firestore.

| Sequência de Ação (runTransaction) | Detalhe Técnico | Falha na Checagem (Passo 2) |
| :--- | :--- | :--- |
| **1. Leitura do Saldo** | `transaction.get(userRef)` | N/A |
| **2. Checagem de Saldo (CRÍTICO)** | `const currentBalance = data.currentBalance; if (currentBalance < costAmount) { throw new Error('Saldo Insuficiente'); }` | A transação é abortada e nenhuma alteração é feita. |
| **3. Cálculo do Novo Saldo** | `const newBalance = currentBalance - costAmount;` | N/A |
| **4. Débito (Escrita 1)** | `transaction.update(userRef, { currentBalance: newBalance, lastUpdated: serverTimestamp() });` | N/A |
| **5. Registro (Escrita 2)** | `transaction.set(transactionRef, { ...dados_com_balanceAfter... });` | N/A |
| **6. Confirmação** | O Firestore aplica **simultaneamente** (atômico) as duas escritas. | Nenhuma mudança é persistida se a escrita falhar em qualquer ponto. |

---

## 7. Análise de Risco (Revisada v1.6)

| Risco | Categoria | Impacto | Mitigação no Protótipo |
| :--- | :--- | :--- | :--- |
| **Integridade do Saldo** | Financeiro/Dados | Alto (Prejuízo ou insatisfação do usuário por concorrência de escrita). | **Transações Atômicas do Firestore** e validação do saldo antes do débito (Passo 2 da Transação). |
| **Custo Google API** | Financeiro | Médio (Custo real se exceder o Free Tier). | Implementar monitoramento de uso (Budgets) no Google Cloud e, se necessário, Caching de resultados no *backend* para consultas repetidas. |
| **Transparência de Custo** | UX/Legal | Médio (Quebra de confiança do Revendedor). | Exibir alertas claros de custo (5 Créditos/Busca, 1 Crédito/Visualização) **antes** de qualquer ação de consumo (RF009). |