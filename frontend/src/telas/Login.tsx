import { useState, type FormEvent } from "react";

import { Erro } from "../App";
import { api, type Usuario } from "../api";

export function Login({ aoEntrar }: { aoEntrar: (usuario: Usuario) => void }) {
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<unknown>(null);
  const [enviando, setEnviando] = useState(false);

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    setErro(null);
    setEnviando(true);
    try {
      aoEntrar(await api.entrar(email.trim(), senha));
    } catch (falha) {
      setErro(falha);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="tela-login">
      <form className="cartao" onSubmit={enviar}>
        <h2>Laudo de Vistoria</h2>
        <p className="fraco">Entre para ver as vistorias e os laudos.</p>
        <Erro erro={erro} />

        <label htmlFor="email">E-mail</label>
        <input
          id="email"
          type="email"
          autoComplete="username"
          inputMode="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />

        <label htmlFor="senha">Senha</label>
        <input
          id="senha"
          type="password"
          autoComplete="current-password"
          value={senha}
          onChange={(e) => setSenha(e.target.value)}
          required
        />

        <div style={{ marginTop: 16 }}>
          <button className="principal" type="submit" disabled={enviando} style={{ width: "100%" }}>
            {enviando ? "Entrando…" : "Entrar"}
          </button>
        </div>
      </form>
    </div>
  );
}
