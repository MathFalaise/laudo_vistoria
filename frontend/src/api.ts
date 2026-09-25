/**
 * Cliente da API.
 *
 * Tudo passa por aqui, e por um motivo: `credentials: "include"` e o
 * tratamento de 401 precisam valer em TODA chamada. Se cada tela fizesse seu
 * próprio fetch, bastaria esquecer um para a sessão parar de ser enviada, ou
 * para um token expirado virar uma tela em branco em vez de voltar ao login.
 *
 * Não existe chave de API deste lado. O navegador fala com este backend; quem
 * fala com o Gemini é o servidor.
 */

export class ErroApi extends Error {
  constructor(public status: number, mensagem: string) {
    super(mensagem);
  }
}

async function requisitar<T>(caminho: string, opcoes: RequestInit = {}): Promise<T> {
  const resposta = await fetch(`/api${caminho}`, {
    ...opcoes,
    credentials: "include",
    headers:
      opcoes.body instanceof FormData
        ? opcoes.headers
        : { "Content-Type": "application/json", ...(opcoes.headers ?? {}) },
  });

  if (resposta.status === 204) return undefined as T;

  const tipo = resposta.headers.get("content-type") ?? "";
  if (!resposta.ok) {
    let detalhe = `Erro ${resposta.status}`;
    if (tipo.includes("application/json")) {
      const corpo = await resposta.json().catch(() => null);
      // O FastAPI devolve erro de validação como lista de objetos.
      if (corpo && typeof corpo.detail === "string") detalhe = corpo.detail;
      else if (Array.isArray(corpo?.detail)) {
        detalhe = corpo.detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join("; ");
      }
    }
    throw new ErroApi(resposta.status, detalhe);
  }

  if (tipo.includes("application/json")) return resposta.json() as Promise<T>;
  return resposta.text() as unknown as T;
}

const get = <T,>(caminho: string) => requisitar<T>(caminho);
const post = <T,>(caminho: string, corpo?: unknown) =>
  requisitar<T>(caminho, { method: "POST", body: corpo ? JSON.stringify(corpo) : undefined });
const patch = <T,>(caminho: string, corpo: unknown) =>
  requisitar<T>(caminho, { method: "PATCH", body: JSON.stringify(corpo) });
const remover = <T,>(caminho: string) => requisitar<T>(caminho, { method: "DELETE" });

// --- tipos ----------------------------------------------------------------

export type Usuario = { id: string; email: string; nome: string };

export type ResumoPendencias = {
  abertas: number;
  por_tipo: Record<string, number>;
  limiar_certeza: number;
};

export type Vistoria = {
  id: string;
  titulo: string;
  endereco: string;
  notas: string;
  data_vistoria: string;
  arquivada: boolean;
  criado_em: string;
  comodos: number;
  fotos: number;
  pendencias: ResumoPendencias;
  lista_comodos?: Comodo[];
};

export type Comodo = {
  id: string;
  nome: string;
  ordem: number;
  estado: "pendente" | "processando" | "concluido" | "falhou";
  erro: string;
  fotos: number;
  fotos_utilizaveis: number;
  cobertura_incompleta: boolean;
  itens: number;
  pendencias_abertas: number;
};

export type Foto = {
  id: string;
  nome_original: string;
  mime: string;
  largura: number;
  altura: number;
  bytes: number;
  ordem: number;
  escopo: "" | "valid" | "partial" | "out_of_scope";
  relevancia: number;
  ambiente_adjacente: boolean;
  reflexo: boolean;
  motivo_escopo: string;
};

export type Regiao = { x: number; y: number; largura: number; altura: number };

export type Evidencia = {
  id: string;
  foto_id: string;
  item_id: string | null;
  categoria: string;
  rotulo: string;
  observacao: string;
  confianca_percepcao: number;
  confianca_escopo: number;
  confianca_final: number;
  reflexo: boolean;
  ambiente_adjacente: boolean;
  status: "aceita" | "descartada" | "em_conflito";
  motivo_descarte: string;
  detalhe_descarte: string;
  regiao: Regiao | null;
};

export type ItemLaudo = {
  id: string;
  texto: string;
  certeza: number;
  motivo: string;
  evidencias: string[];
};

export type Laudo = {
  vistoria: string;
  texto: string;
  comodos: {
    id: string;
    nome: string;
    estado: string;
    cobertura_incompleta: boolean;
    categorias: { categoria: string; rotulo: string; itens: ItemLaudo[] }[];
  }[];
};

export type Pendencia = {
  id: string;
  comodo_id: string;
  comodo: string;
  categoria: string;
  rotulo: string;
  tipo: "certeza" | "falta" | "repetido" | "scope_conflict";
  motivo: string;
  certeza: number;
  item_id: string | null;
  item_texto: string;
  texto_proposto: string;
  decisao: string;
  correcao: string;
  evidencias: Evidencia[];
  fotos: string[];
};

export type Job = {
  id: string;
  vistoria_id: string;
  tipo: string;
  estado: "pending" | "processing" | "completed" | "failed" | "cancelled";
  total: number;
  concluidos: number;
  mensagem: string;
  erro: string;
  usar_evidencias: boolean;
  criado_em: string;
};

export type Regra = {
  id: string;
  texto: string;
  ativa: boolean;
  origem: string;
  adotada_em: string | null;
};

export type ResultadoUpload = {
  aceitas: Foto[];
  recusadas: { nome: string; motivo: string }[];
};

// --- chamadas -------------------------------------------------------------

export const api = {
  entrar: (email: string, senha: string) => post<Usuario>("/auth/login", { email, senha }),
  sair: () => post<{ ok: boolean }>("/auth/logout"),
  eu: () => get<Usuario>("/auth/eu"),

  vistorias: () => get<Vistoria[]>("/vistorias"),
  vistoria: (id: string) => get<Vistoria>(`/vistorias/${id}`),
  criarVistoria: (dados: { titulo: string; endereco?: string; notas?: string; data_vistoria?: string }) =>
    post<Vistoria>("/vistorias", dados),
  editarVistoria: (id: string, dados: { titulo: string; endereco: string; notas: string; data_vistoria: string }) =>
    patch<Vistoria>(`/vistorias/${id}`, dados),
  apagarVistoria: (id: string) => remover<{ ok: boolean }>(`/vistorias/${id}`),

  criarComodo: (vistoriaId: string, nome: string) =>
    post<{ id: string; nome: string }>(`/vistorias/${vistoriaId}/comodos`, { nome }),
  apagarComodo: (id: string) => remover<{ ok: boolean }>(`/comodos/${id}`),

  fotos: (comodoId: string) => get<Foto[]>(`/comodos/${comodoId}/fotos`),
  enviarFotos: (comodoId: string, arquivos: File[]) => {
    const dados = new FormData();
    arquivos.forEach((arquivo) => dados.append("arquivos", arquivo));
    return requisitar<ResultadoUpload>(`/comodos/${comodoId}/fotos`, {
      method: "POST",
      body: dados,
    });
  },
  apagarFoto: (id: string) => remover<{ ok: boolean }>(`/fotos/${id}`),
  enviarZip: (vistoriaId: string, arquivo: File) => {
    const dados = new FormData();
    dados.append("arquivo", arquivo);
    return requisitar<{ comodos: { comodo: string; fotos: number }[]; recusadas: { nome: string; motivo: string }[] }>(
      `/vistorias/${vistoriaId}/zip`,
      { method: "POST", body: dados },
    );
  },
  urlMiniatura: (fotoId: string, lado = 480) => `/api/fotos/${fotoId}/miniatura?lado=${lado}`,
  urlFoto: (fotoId: string) => `/api/fotos/${fotoId}/arquivo`,

  processar: (vistoriaId: string, corpo: { comodos?: string[]; usar_evidencias: boolean; reprocessar_concluidos?: boolean }) =>
    post<Job>(`/vistorias/${vistoriaId}/processar`, corpo),
  job: (id: string) => get<Job>(`/jobs/${id}`),
  cancelarJob: (id: string) => post<Job>(`/jobs/${id}/cancelar`),

  laudo: (vistoriaId: string) => get<Laudo>(`/vistorias/${vistoriaId}/laudo`),
  editarItem: (itemId: string, texto: string) => patch<ItemLaudo>(`/itens/${itemId}`, { texto }),

  evidencias: (comodoId: string) => get<Evidencia[]>(`/comodos/${comodoId}/evidencias`),

  pendencias: (vistoriaId: string, abertas = true) =>
    get<Pendencia[]>(`/vistorias/${vistoriaId}/pendencias?abertas=${abertas}`),
  decidir: (
    pendenciaId: string,
    corpo: { decisao: string; correcao?: string; regra?: string; tipo_correcao?: string; razao?: string },
  ) => post<{ acao: string; regra_adotada: string | null }>(`/pendencias/${pendenciaId}/decisao`, corpo),

  regras: () => get<Regra[]>("/regras"),
  criarRegra: (texto: string) => post<Regra>("/regras", { texto }),
  desativarRegra: (id: string) => post<Regra>(`/regras/${id}/desativar`),

  urlLaudoTxt: (vistoriaId: string) => `/api/vistorias/${vistoriaId}/exportar/laudo.txt`,
  urlZip: (vistoriaId: string) => `/api/vistorias/${vistoriaId}/exportar/vistoria.zip`,
};
