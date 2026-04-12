/**
 * Conteúdo dos guias de uso de cada simulador.
 * Para adicionar ou editar: altere APENAS este arquivo.
 *
 * Última revisão de conteúdo: Abril 2026
 * Base normativa: EC 132/2023 · LC 214/2025 · LC 227/2026
 */

export const ULTIMA_REVISAO = "Abril 2026";

export const GUIA_CARGA_RT = {
  campos: [
    {
      campo: "Faturamento anual (R$)",
      descricao: "Receita bruta anual da empresa.",
      exemplo: "10000000 para R$ 10M/ano",
    },
    {
      campo: "Regime tributário",
      descricao: "Lucro Real, Presumido ou Simples — define as alíquotas do regime atual para comparação.",
    },
    {
      campo: "Tipo de operação",
      descricao: "Produto (indústria/comércio), Serviço ou Misto — determina qual base de cálculo do IBS/CBS se aplica.",
    },
    {
      campo: "% Exportação (0-100)",
      descricao: "Percentual do faturamento destinado à exportação. Exportações têm imunidade no novo regime — quanto maior, menor a carga projetada.",
      exemplo: "0 para venda só no mercado interno",
    },
    {
      campo: "% Aproveitamento créditos (0-100)",
      descricao: "Quanto dos créditos de IBS/CBS você consegue aproveitar na prática. 100 = aproveitamento total da cadeia.",
      exemplo: "100 para empresa com cadeia completa de crédito",
    },
  ],
  observacao:
    "O resultado é uma estimativa baseada nas alíquotas de referência da LC 214/2025. Alíquotas definitivas dependem de regulamentação do CGIBS.",
};

export const GUIA_SPLIT_PAYMENT = {
  campos: [
    {
      campo: "Faturamento mensal (R$)",
      descricao: "Receita bruta média mensal da empresa.",
    },
    {
      campo: "Prazo médio de recebimento",
      descricao: "Dias entre emissão da NF-e e efetivo recebimento. Quanto maior o prazo, maior o impacto no caixa.",
      exemplo: "30 dias para boleto, 2 dias para cartão à vista",
    },
    {
      campo: "Mix de recebimento",
      descricao: "Percentual de cada meio de pagamento (cartão, boleto, PIX, dinheiro). O split payment incide diferente por meio.",
    },
    {
      campo: "% B2B / B2C",
      descricao: "Percentual de vendas para empresas (B2B) vs. consumidores finais (B2C). Afeta a modalidade de split aplicável.",
    },
  ],
  observacao:
    "O impacto no capital de giro é calculado com base na modalidade Split Inteligente (art. 31 da LC 214/2025). Modalidades simplificada e de contingência têm impactos diferentes.",
};

export const GUIA_CREDITOS = {
  campos: [
    {
      campo: "Volume mensal de compras (R$)",
      descricao: "Total de compras de insumos, serviços e ativo imobilizado com direito a crédito de IBS/CBS.",
    },
    {
      campo: "% Compras com direito a crédito",
      descricao: "Percentual do volume de compras que se qualifica como crédito. Depende do tipo de insumo e do fornecedor.",
      exemplo: "80% se parte dos fornecedores estiver no Simples (sem repasse de crédito)",
    },
    {
      campo: "Tipo de atividade",
      descricao: "Indústria, comércio ou serviço — define as regras de creditamento aplicáveis.",
    },
  ],
  observacao:
    "Créditos de ICMS acumulados têm regras de aproveitamento específicas na transição (2029-2033). Este simulador foca no crédito de IBS/CBS no regime permanente.",
};

export const GUIA_REESTRUTURACAO = {
  campos: [
    {
      campo: "UF de origem da operação",
      descricao: "Estado onde a empresa está localizada atualmente.",
    },
    {
      campo: "UF de destino predominante",
      descricao: "Estado para onde a maioria das vendas é destinada. No novo regime, o IBS é recolhido no destino — isso muda a equação de benefícios fiscais.",
    },
    {
      campo: "Tipo de reestruturação",
      descricao: "Mudança de localização, segregação de atividades, revisão de cadeia produtiva ou combinação.",
    },
    {
      campo: "Faturamento anual (R$)",
      descricao: "Base para calcular o ganho potencial da reestruturação em valor absoluto.",
    },
  ],
  observacao:
    "Reestruturação societária envolve custos jurídicos, contábeis e operacionais não computados nesta estimativa. Use como referência de magnitude, não como projeção definitiva.",
};

export const GUIA_IMPACTO_IS = {
  alertaCritico:
    "Alíquotas do IS ainda não regulamentadas pelo Congresso. Os valores usados nesta simulação são estimativas de mercado — não representam posição normativa vigente.",
  campos: [
    {
      campo: "Categoria do produto",
      descricao: "Veículos, bebidas alcoólicas, tabaco, produtos prejudiciais à saúde ou ao meio ambiente — cada categoria terá alíquota específica.",
    },
    {
      campo: "NCM (opcional)",
      descricao: "Código da Nomenclatura Comum do Mercosul. Quando informado, permite estimativa mais precisa por produto.",
      exemplo: "2202.10.00 para refrigerantes",
    },
    {
      campo: "Volume mensal (R$ ou unidades)",
      descricao: "Quantidade ou valor de produção/comercialização mensal para base de cálculo do IS.",
    },
  ],
  observacao:
    "O IS incide sobre produção e importação — não sobre toda a cadeia. Verifique se sua empresa é contribuinte direto antes de usar esta estimativa.",
};
