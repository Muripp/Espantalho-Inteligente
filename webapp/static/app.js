// VIGIA · dashboard
// Vault: "03 Webapp/Dashboard". Atualiza sozinho (polling) e faz o "Testar pasta".

const ANIMAIS = {
  ave:          { e: "🐦", n: "Ave",          c: "#e0a106" },
  cachorro:     { e: "🐕", n: "Cachorro",     c: "#e5484d" },
  porco:        { e: "🐖", n: "Porco",        c: "#d6409f" },
  cavalo:       { e: "🐎", n: "Cavalo",       c: "#a0662b" },
  rato:         { e: "🐀", n: "Rato",         c: "#6f6e77" },
  vaca:         { e: "🐄", n: "Vaca",         c: "#0090ff" },
  gato:         { e: "🐈", n: "Gato",         c: "#8e4ec6" },
  outro_animal: { e: "🦓", n: "Outro animal", c: "#5b8a72" },
  pessoa:       { e: "🧍", n: "Pessoa",       c: "#30a46c" },
};
const ORDEM = ["ave", "cachorro", "porco", "cavalo", "rato", "vaca", "gato", "outro_animal", "pessoa"];
const DECISOES = {
  espantou: "🔊 espantou", pessoa_perto: "🛡️ pessoa perto", aguardando: "⏳ aguardando", nada: "nada",
};
const ACOES = { som: "🔊", led: "💡", rele: "💧", servo: "⚙️", parar: "⏹" };
const EXT_IMAGEM = /\.(jpe?g|png|webp|bmp)$/i;

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const animal = (k) => ANIMAIS[k] || { e: "❔", n: k || "—", c: "#999" };
const pct = (x) => (x == null ? "" : Math.round(x * 100) + "%");
const dorme = (ms) => new Promise((r) => setTimeout(r, ms));

function fmtData(ms) {
  if (!ms) return "—";
  return new Date(ms).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
function fmtHora(ms) {
  return ms ? new Date(ms).toLocaleTimeString("pt-BR") : "—";
}
function atras(ms) {
  const s = Math.round((Date.now() - ms) / 1000);
  if (s < 5) return "agora";
  if (s < 60) return `há ${s} s`;
  if (s < 3600) return `há ${Math.floor(s / 60)} min`;
  if (s < 86400) return `há ${Math.floor(s / 3600)} h`;
  return fmtData(ms);
}
async function api(url, opcoes) {
  const r = await fetch(url, opcoes);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.status === 204 ? null : r.json();
}
function guardar(chave, valor) { try { localStorage.setItem(chave, valor); } catch (_) {} }
function ler(chave) { try { return localStorage.getItem(chave); } catch (_) { return null; } }

function htmlAnimal(a, conf) {
  if (!a) return '<span class="outras">—</span>';
  const m = animal(a);
  const barra = conf != null
    ? `<span class="conf" style="--cor:${m.c}"><i style="width:${Math.round(conf * 100)}%"></i></span> <span class="conf-txt">${pct(conf)}</span>`
    : "";
  return `<span class="animal">${m.e} ${esc(m.n)}</span>${barra}`;
}
const htmlDecisao = (d) => `<span class="decisao ${esc(d)}">${esc(DECISOES[d] || d)}</span>`;
const fotoUrl = (a) => (a.foto ? `/fotos/${encodeURIComponent(a.foto)}` : "");

// =================== estado ===================
const estado = {
  periodo: Number(ler("vigia.periodo") || 24),
  status: null,
  grafico: null,
  lote: null,               // { id, nome }
  envio: null,              // { total, enviadas, ignoradas, cancelado, rodando }
  loteInfo: null,
  loteAnalises: [],
  ultimaContagem: -1,
  filtro: "",
  analisesPorId: new Map(),
};

// =================== visão geral (a cada 2 s) ===================
async function atualizarGeral() {
  try {
    const [status, resumo, feed, cmds] = await Promise.all([
      api("/api/status"),
      api(`/api/resumo?horas=${estado.periodo}`),
      api("/api/analises?limite=25"),
      api("/api/eventos-esp32?limite=15"),
    ]);
    estado.status = status;
    feed.forEach((a) => estado.analisesPorId.set(a.id, a));
    renderStatus(status);
    renderCartoes(resumo);
    renderGrafico(resumo.por_hora);
    renderFeed(feed);
    renderEventosESP32(cmds);
  } catch (e) {
    renderStatus(null);
    console.warn(e);
  }
}

function renderStatus(s) {
  const el = $("status-proc");
  if (!s) {
    el.className = "pilula off";
    el.lastElementChild.textContent = "webapp sem resposta";
    return;
  }
  el.className = "pilula " + (s.processador_online ? "on" : "off");
  el.lastElementChild.textContent = s.processador_online
    ? `processador online${s.fila_imagens ? ` · ${s.fila_imagens} na fila` : ""}`
    : `processador offline${s.ultimo_contato_processador ? ` · visto ${atras(s.ultimo_contato_processador)}` : ""}`;
}

function renderCartoes(r) {
  const nomes = { 1: "na última hora", 24: "nas últimas 24 h", 168: "nos últimos 7 dias", 0: "no total" };
  let html = `<div class="cartao total"><div class="emoji">📷</div><div class="n">${r.total}</div>
      <div class="rotulo">análises registradas ${nomes[estado.periodo] || ""}</div></div>`;
  html += `<div class="cartao" style="--cor:#2f6b3a"><div class="emoji">🔊</div><div class="n">${r.por_decisao.espantou || 0}</div>
      <div class="rotulo">sustos disparados</div></div>`;
  for (const k of ORDEM) {
    const n = r.por_animal[k] || 0;
    const m = animal(k);
    html += `<div class="cartao ${n ? "" : "zero"}" style="--cor:${m.c}"><div class="emoji">${m.e}</div>
      <div class="n">${n}</div><div class="rotulo">${esc(m.n)}</div></div>`;
  }
  $("cartoes").innerHTML = html;
}

function renderGrafico(porHora) {
  if (!window.Chart) return;   // sem internet o CDN não carrega: só esconde o gráfico
  let chaves;
  if (estado.periodo === 1 || estado.periodo === 24) {
    chaves = [];
    const h = new Date(); h.setMinutes(0, 0, 0);
    for (let i = estado.periodo === 1 ? 1 : 23; i >= 0; i--) {
      const d = new Date(h.getTime() - i * 3600e3);
      const p = (x) => String(x).padStart(2, "0");
      chaves.push(`${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:00`);
    }
  } else {
    chaves = Object.keys(porHora).sort();
  }
  const rotulos = chaves.map((k) => (estado.periodo <= 24 ? k.slice(11) : `${k.slice(8, 10)}/${k.slice(5, 7)} ${k.slice(11, 13)}h`));
  const conjuntos = ORDEM.filter((a) => a !== "pessoa" && chaves.some((k) => porHora[k]?.[a]))
    .map((a) => ({ label: `${animal(a).e} ${animal(a).n}`, data: chaves.map((k) => porHora[k]?.[a] || 0),
                   backgroundColor: animal(a).c, borderRadius: 3, maxBarThickness: 26 }));
  const escuro = matchMedia("(prefers-color-scheme: dark)").matches;
  const corTexto = escuro ? "#9aa293" : "#6b7166";
  if (!estado.grafico) {
    estado.grafico = new Chart($("grafico-horas"), {
      type: "bar",
      data: { labels: rotulos, datasets: conjuntos },
      options: {
        animation: false, maintainAspectRatio: false,
        plugins: { legend: { position: "bottom", labels: { boxWidth: 10, color: corTexto } } },
        scales: {
          x: { stacked: true, grid: { display: false }, ticks: { color: corTexto, maxRotation: 0, autoSkip: true } },
          y: { stacked: true, beginAtZero: true, ticks: { precision: 0, color: corTexto }, grid: { color: escuro ? "#2c3127" : "#eceee8" } },
        },
      },
    });
  } else {
    estado.grafico.data.labels = rotulos;
    estado.grafico.data.datasets = conjuntos;
    estado.grafico.update();
  }
}

function renderFeed(lista) {
  if (!lista.length) {
    $("feed").innerHTML = '<li class="vazio-lista">Nada analisado ainda. Teste uma pasta aí em cima 👆</li>';
    return;
  }
  $("feed").innerHTML = lista.map((a) => `
    <li data-id="${esc(a.id)}">
      ${a.foto ? `<img class="mini" loading="lazy" src="${fotoUrl(a)}" alt="">` : '<div class="mini"></div>'}
      <div>
        <div class="linha1">${htmlAnimal(a.animal, a.confianca)} ${htmlDecisao(a.decisao)}</div>
        <div class="linha2">${esc(a.arquivo || a.origem)} · ${esc(a.gatilho)}${a.resposta ? ` · resposta <b>${esc(a.resposta)}</b>` : ""}</div>
      </div>
      <span class="quando" title="${fmtData(a.ts)}">${atras(a.ts)}</span>
    </li>`).join("");
}

function resumoParams(p) {
  return Object.entries(p || {}).map(([k, v]) => `${k} ${v}`).join(" · ");
}
const htmlAcoes = (acoes) => (acoes || []).map((x) => `${ACOES[x.acao] || "•"}${esc(x.acao)}`).join(" + ");
function renderEventosESP32(lista) {
  if (!lista.length) {
    $("comandos").innerHTML = '<li class="vazio-lista">Nenhum evento ainda.</li>';
    return;
  }
  $("comandos").innerHTML = lista.map((ev) => {
    const m = animal(ev.animal);
    const alvo = [...new Set((ev.acoes || []).map((x) => x.esp32))].join(", ");
    return `<li>
      <span class="acao-icone" style="background:${m.c}22">${m.e}</span>
      <div><b>${esc(m.n)}</b> → resposta <b>${esc(ev.resposta)}</b>
        <div class="cmd-resumo">${htmlAcoes(ev.acoes)} · ${esc(alvo)}</div></div>
      <div style="text-align:right"><div class="st ${esc(ev.status)}">${ev.status === "executado" ? "✓ " : ""}${esc(ev.status)}</div>
        <div class="cmd-resumo">${fmtHora(ev.ts)}</div></div>
    </li>`;
  }).join("");
}

// =================== testar pasta ===================
async function carregarLotes() {
  const lotes = await api("/api/lotes");
  const sel = $("lotes-anteriores");
  sel.innerHTML = '<option value="">testes anteriores…</option>' + lotes.map((l) =>
    `<option value="${esc(l.id)}">${esc(l.nome)} · ${l.total} fotos · ${fmtData(l.criado_em)}</option>`).join("");
  if (estado.lote) sel.value = estado.lote.id;
}

function abrirLote(id, nome) {
  estado.lote = { id, nome };
  estado.ultimaContagem = -1;
  estado.loteAnalises = [];
  estado.filtro = "";
  guardar("vigia.lote", id);
  $("teste-vazio").hidden = true;
  $("teste-ativo").hidden = false;
  $("lote-nome").textContent = "📁 " + (nome || id);
  $("btn-csv").href = `/api/lotes/${encodeURIComponent(id)}/csv`;
  $("tabela-corpo").innerHTML = "";
  atualizarLote();
}

async function selecionouPasta(ev) {
  const todos = [...ev.target.files];
  ev.target.value = "";
  const imagens = todos.filter((f) => EXT_IMAGEM.test(f.name))
    .sort((a, b) => (a.webkitRelativePath || a.name).localeCompare(b.webkitRelativePath || b.name, "pt-BR", { numeric: true }));
  if (!imagens.length) {
    alert(`Nenhuma imagem (.jpg, .png, .webp, .bmp) nessa pasta${todos.length ? ` (${todos.length} arquivos de outros tipos)` : ""}.`);
    return;
  }
  if (estado.envio?.rodando) estado.envio.cancelado = true;
  const nome = (imagens[0].webkitRelativePath || "pasta").split("/")[0];
  const { id } = await api("/api/lotes", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nome, total: imagens.length }),
  });
  abrirLote(id, nome);
  carregarLotes();
  enviarImagens(id, imagens);
}

// Reduz a foto no navegador (lado máximo 1280 px) antes de enviar: upload mais rápido,
// e o modelo trabalha em 640 px de qualquer jeito.
async function reduzir(arquivo) {
  try {
    const bmp = await createImageBitmap(arquivo);
    const esc = Math.min(1, 1280 / Math.max(bmp.width, bmp.height));
    if (esc === 1 && /jpe?g$/i.test(arquivo.name)) { bmp.close?.(); return arquivo; }
    const c = document.createElement("canvas");
    c.width = Math.round(bmp.width * esc);
    c.height = Math.round(bmp.height * esc);
    c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
    bmp.close?.();
    return await new Promise((r) => c.toBlob(r, "image/jpeg", 0.9));
  } catch (_) {
    return null;   // formato que o navegador não abre
  }
}

async function enviarImagens(idLote, imagens) {
  const envio = { idLote, total: imagens.length, enviadas: 0, ignoradas: 0, cancelado: false, rodando: true };
  estado.envio = envio;
  let i = 0;
  const trabalhador = async () => {
    while (i < imagens.length && !envio.cancelado) {
      // não deixa a fila crescer demais: espera o processador alcançar
      while (!envio.cancelado && estado.loteInfo?.id === idLote && (envio.enviadas - estado.loteInfo.processadas) >= 12) {
        await dorme(300);
      }
      if (envio.cancelado || i >= imagens.length) break;   // outro trabalhador pegou a última
      const f = imagens[i++];
      const blob = await reduzir(f);
      if (!blob) { envio.ignoradas++; continue; }
      const form = new FormData();
      form.append("arquivo", blob, f.name);
      form.append("lote", idLote);
      form.append("nome", f.webkitRelativePath || f.name);
      form.append("data_arquivo", String(f.lastModified));
      try {
        await api("/api/simulador/imagem", { method: "POST", body: form });
        envio.enviadas++;
      } catch (e) {
        envio.ignoradas++;
        console.warn(e);
      }
    }
  };
  await Promise.all([trabalhador(), trabalhador(), trabalhador()]);
  envio.rodando = false;
}

async function atualizarLote() {
  if (!estado.lote) return;
  let l;
  try {
    l = await api(`/api/lotes/${encodeURIComponent(estado.lote.id)}`);
  } catch (_) {
    return;
  }
  estado.loteInfo = l;
  const envio = estado.envio?.idLote === l.id ? estado.envio : null;
  const enviadas = envio ? envio.enviadas : l.enviadas;
  const total = l.total || 1;
  $("barra-enviadas").style.width = `${(100 * enviadas) / total}%`;
  $("barra-processadas").style.width = `${(100 * l.processadas) / total}%`;

  const partes = [`<b>${l.processadas}</b> de ${l.total} processadas`];
  if (envio?.rodando) partes.push(`${enviadas} enviadas`);
  if (l.na_fila) partes.push(`${l.na_fila} na fila`);
  if (envio?.ignoradas) partes.push(`${envio.ignoradas} ignoradas (formato não suportado)`);
  if (l.tempo_medio_ms) partes.push(`modelo: ${l.tempo_medio_ms} ms/foto em média`);
  if (envio?.cancelado) partes.push("parado");
  else if (l.processadas >= l.total) partes.push("✅ concluído");
  partes.push(`iniciado ${fmtData(l.criado_em)}`);
  $("lote-info").innerHTML = partes.join(" · ");
  $("btn-cancelar").hidden = !(envio?.rodando || l.na_fila);
  $("aviso-offline").hidden = !(l.na_fila > 0 && estado.status && !estado.status.processador_online);

  renderChipsLote(l);
  if (l.processadas !== estado.ultimaContagem) {
    estado.ultimaContagem = l.processadas;
    const lista = await api(`/api/analises?lote=${encodeURIComponent(l.id)}&limite=5000`);
    lista.reverse();   // ordem em que foram processadas
    lista.forEach((a) => estado.analisesPorId.set(a.id, a));
    estado.loteAnalises = lista;
    renderTabela();
  }
}

function renderChipsLote(l) {
  const chips = [];
  for (const k of [...ORDEM, "nada"]) {
    const n = l.por_animal[k];
    if (!n) continue;
    const m = k === "nada" ? { e: "∅", n: "sem animal", c: "#bbb" } : animal(k);
    chips.push(`<span class="chip ${estado.filtro === k ? "ativo" : ""}" data-filtro="${k}" style="--cor:${m.c}">
      <span class="ponto"></span>${m.e} ${esc(m.n)} <b>${n}</b></span>`);
  }
  for (const [d, n] of Object.entries(l.por_decisao)) {
    if (d === "nada") continue;
    chips.push(`<span class="chip" title="decisão">${esc(DECISOES[d] || d)} <b>${n}</b></span>`);
  }
  $("lote-resumo").innerHTML = chips.join("");
  const sel = $("filtro-animal");
  const atual = estado.filtro;
  sel.innerHTML = '<option value="">todos</option>' + Object.keys(l.por_animal).map((k) =>
    `<option value="${esc(k)}">${k === "nada" ? "sem animal" : esc(animal(k).n)}</option>`).join("");
  sel.value = atual;
}

function renderTabela() {
  const f = estado.filtro;
  const lista = estado.loteAnalises.filter((a) => !f || (f === "nada" ? !a.animal : a.animal === f));
  $("tabela-contagem").textContent = `${lista.length} foto${lista.length === 1 ? "" : "s"}`;
  $("tabela-corpo").innerHTML = lista.map((a) => {
    const outras = a.deteccoes.slice(a.animal ? 1 : 0)
      .map((d) => `${animal(d.classe).e} ${pct(d.confianca)}`).join(" ");
    const cmds = htmlAcoes(a.evento?.acoes);
    return `<tr data-id="${esc(a.id)}">
      <td>${a.foto ? `<img class="mini" loading="lazy" src="${fotoUrl(a)}" alt="">` : ""}</td>
      <td class="arquivo" title="${esc(a.arquivo)}">${esc(a.arquivo)}</td>
      <td>${htmlAnimal(a.animal, a.confianca)}</td>
      <td>${htmlDecisao(a.decisao)}</td>
      <td>${a.resposta ? `<b>${esc(a.resposta)}</b><div class="cmd-resumo">${cmds}</div>` : '<span class="outras">—</span>'}</td>
      <td class="outras">${outras || "—"}</td>
      <td class="data">${fmtData(a.data_arquivo)}</td>
      <td class="data">${fmtHora(a.ts)}</td>
      <td class="num">${a.tempo_deteccao ?? "—"} ms</td>
    </tr>`;
  }).join("");
}

// =================== importar memória do Pi ===================
// Lê memoria/eventos.jsonl (+ memoria/fotos/) gravados pelo processador e manda cada
// evento pro POST /api/analises, como se o Pi tivesse publicado. Importar 2x não duplica (mesmo id).
function lerBase64(arquivo) {
  return new Promise((ok, erro) => {
    const r = new FileReader();
    r.onload = () => ok(String(r.result).split(",")[1]);
    r.onerror = erro;
    r.readAsDataURL(arquivo);
  });
}
async function importarMemoria(ev) {
  const arquivos = [...ev.target.files];
  ev.target.value = "";
  const jsonl = arquivos.find((f) => f.name === "eventos.jsonl");
  if (!jsonl) { alert("Não achei o eventos.jsonl. Escolha a pasta 'memoria' do processador."); return; }
  const fotos = new Map(arquivos.map((f) => [(f.webkitRelativePath || f.name).split("/").slice(1).join("/"), f]));
  const linhas = (await jsonl.text()).split("\n").filter((l) => l.trim());
  const botao = $("btn-memoria");
  botao.disabled = true;
  let ok = 0, falhas = 0;
  for (const [i, linha] of linhas.entries()) {
    botao.textContent = `📥 importando ${i + 1}/${linhas.length}…`;
    try {
      const d = JSON.parse(linha);
      const foto = d.foto && fotos.get(d.foto);
      if (foto) d.foto_jpeg_b64 = await lerBase64(foto);
      await api("/api/analises", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(d) });
      ok++;
    } catch (e) { falhas++; console.warn(e); }
  }
  botao.disabled = false;
  botao.textContent = "📥 Importar memória do Pi";
  alert(`${ok} eventos importados${falhas ? `, ${falhas} com erro` : ""}.`);
  atualizarGeral();
}

// =================== detalhe (modal) ===================
function abrirModal(id) {
  const a = estado.analisesPorId.get(id);
  if (!a) return;
  $("modal-foto").src = fotoUrl(a);
  $("modal-foto").hidden = !a.foto;
  const m = a.animal ? animal(a.animal) : null;
  $("modal-info").innerHTML = `
    <h3>${m ? `${m.e} ${esc(m.n)} <span class="conf-txt">${pct(a.confianca)}</span>` : "Nenhum animal"}</h3>
    ${htmlDecisao(a.decisao)} ${a.resposta ? ` resposta <b>${esc(a.resposta)}</b>` : ""}
    <dl>
      <dt>Arquivo</dt><dd>${esc(a.arquivo || "—")}</dd>
      <dt>Data do arquivo</dt><dd>${fmtData(a.data_arquivo)}</dd>
      <dt>Processado em</dt><dd>${fmtData(a.ts)}</dd>
      <dt>Origem</dt><dd>${esc(a.origem)} · gatilho ${esc(a.gatilho)}</dd>
      <dt>Tamanho</dt><dd>${a.largura}×${a.altura} px</dd>
      <dt>Tempo</dt><dd>modelo ${a.tempo_deteccao} ms · total ${a.tempo_total} ms</dd>
      <dt>Modelo</dt><dd>${esc(a.modelo)}</dd>
      <dt>Dispositivo</dt><dd>${esc(a.dispositivo)}</dd>
      <dt>ID</dt><dd>${esc(a.id)}</dd>
    </dl>
    <h4>Detecções (${a.deteccoes.length})</h4>
    ${a.deteccoes.length ? `<ul>${a.deteccoes.map((d) => `<li>${htmlAnimal(d.classe, d.confianca)}
        <span class="outras">caixa ${d.caixa.join(", ")}</span></li>`).join("")}</ul>` : '<p class="outras">nenhuma acima do corte de confiança</p>'}
    <h4>Evento enviado pro ESP32</h4>
    ${a.evento ? `<p class="outras">${esc(a.evento.id)} · <span class="st ${esc(a.evento.status)}">${esc(a.evento.status)}</span></p>
      <ul>${a.evento.acoes.map((x) => `<li>${ACOES[x.acao] || ""} <b>${esc(x.acao)}</b> → ${esc(x.esp32)}
        <span class="outras">${esc(resumoParams(x.params))}</span></li>`).join("")}</ul>`
      : `<p class="outras">nenhum${a.decisao === "pessoa_perto" ? " (tinha pessoa perto)" : a.decisao === "aguardando" ? " (esperando o cooldown)" : ""}</p>`}`;
  $("modal").hidden = false;
}
function fecharModal() { $("modal").hidden = true; }

// =================== eventos ===================
$("periodo").value = String(estado.periodo);
$("periodo").addEventListener("change", (e) => {
  estado.periodo = Number(e.target.value);
  guardar("vigia.periodo", e.target.value);
  atualizarGeral();
});
$("btn-pasta").addEventListener("click", () => $("input-pasta").click());
$("btn-memoria").addEventListener("click", () => $("input-memoria").click());
$("input-memoria").addEventListener("change", importarMemoria);
$("input-pasta").addEventListener("change", selecionouPasta);
$("btn-cancelar").addEventListener("click", async () => {
  if (estado.envio) estado.envio.cancelado = true;
  if (estado.lote) await api(`/api/lotes/${encodeURIComponent(estado.lote.id)}/cancelar`, { method: "POST" });
  atualizarLote();
});
$("lotes-anteriores").addEventListener("change", (e) => {
  const op = e.target.selectedOptions[0];
  if (e.target.value) abrirLote(e.target.value, op.textContent.split(" · ")[0]);
});
$("filtro-animal").addEventListener("change", (e) => { estado.filtro = e.target.value; renderTabela(); atualizarLote(); });
$("lote-resumo").addEventListener("click", (e) => {
  const chip = e.target.closest("[data-filtro]");
  if (!chip) return;
  estado.filtro = estado.filtro === chip.dataset.filtro ? "" : chip.dataset.filtro;
  $("filtro-animal").value = estado.filtro;
  renderTabela();
  renderChipsLote(estado.loteInfo);
});
$("btn-limpar").addEventListener("click", async () => {
  if (!confirm("Apagar TODAS as análises, fotos e testes do banco do dashboard?\n(O modelo e as suas fotos originais não são afetados.)")) return;
  await api("/api/limpar", { method: "POST" });
  estado.lote = null;
  guardar("vigia.lote", "");
  $("teste-ativo").hidden = true;
  $("teste-vazio").hidden = false;
  carregarLotes();
  atualizarGeral();
});
for (const id of ["feed", "tabela-corpo"]) {
  $(id).addEventListener("click", (e) => {
    const el = e.target.closest("[data-id]");
    if (el) abrirModal(el.dataset.id);
  });
}
$("modal").addEventListener("click", (e) => { if (e.target.id === "modal") fecharModal(); });
$("modal-fechar").addEventListener("click", fecharModal);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") fecharModal(); });

// =================== início ===================
(async function iniciar() {
  await carregarLotes().catch(() => {});
  const salvo = ler("vigia.lote");
  const op = salvo && [...$("lotes-anteriores").options].find((o) => o.value === salvo);
  if (op) abrirLote(salvo, op.textContent.split(" · ")[0]);
  atualizarGeral();
  setInterval(atualizarGeral, 2000);
  setInterval(atualizarLote, 1000);
})();
