BEGIN;

-- Tabela de heurísticas extraídas de casos encerrados (Motor de Aprendizado Institucional, G24)
CREATE TABLE IF NOT EXISTS heuristicas (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Origem
    caso_origem_id   UUID         REFERENCES monitoramento_p6(id),
    dossie_id        INTEGER      REFERENCES outputs(id),
    user_id          UUID         REFERENCES users(id),

    -- Conteúdo
    titulo           VARCHAR(200) NOT NULL,
    descricao        TEXT         NOT NULL,
    tipo             VARCHAR(30)  NOT NULL,
    -- 'premissa_estavel' | 'risco_materializado' | 'divergencia_gestor_melhor'
    -- | 'divergencia_ia_melhor' | 'padrao_setor'

    -- Contexto de origem
    tags             TEXT[]       NOT NULL DEFAULT '{}',
    normas_base      TEXT[]       NOT NULL DEFAULT '{}',

    -- Métricas
    acuracia_projecao     NUMERIC(5,4) DEFAULT NULL,
    riscos_materializados NUMERIC(5,4) DEFAULT NULL,
    premissas_estaveis    NUMERIC(5,4) DEFAULT NULL,

    -- Salvaguardas DC v7
    valida_ate       DATE         NOT NULL,
    status           VARCHAR(20)  NOT NULL DEFAULT 'ativa',
    -- 'ativa' | 'expirada' | 'revisao_pendente' | 'invalidada'
    motivo_invalidacao TEXT        DEFAULT NULL,

    -- Auditoria
    criado_em        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    validada_em      TIMESTAMPTZ  DEFAULT NULL,
    validada_por     UUID         REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_heur_user   ON heuristicas (user_id);
CREATE INDEX IF NOT EXISTS idx_heur_tipo   ON heuristicas (tipo);
CREATE INDEX IF NOT EXISTS idx_heur_status ON heuristicas (status);
CREATE INDEX IF NOT EXISTS idx_heur_tags   ON heuristicas USING gin(tags);
CREATE INDEX IF NOT EXISTS idx_heur_normas ON heuristicas USING gin(normas_base);

-- Métricas agregadas de aprendizado por usuário/mês
CREATE TABLE IF NOT EXISTS metricas_aprendizado (
    id                          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                     UUID        REFERENCES users(id),
    periodo                     DATE        NOT NULL,
    total_casos                 INT         NOT NULL DEFAULT 0,
    casos_encerrados            INT         NOT NULL DEFAULT 0,
    acuracia_media              NUMERIC(5,4) DEFAULT NULL,
    divergencias_gestor_correto INT         NOT NULL DEFAULT 0,
    divergencias_ia_correto     INT         NOT NULL DEFAULT 0,
    heuristicas_geradas         INT         NOT NULL DEFAULT 0,
    atualizado_em               TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (user_id, periodo)
);

COMMIT;
