/* =========================================================
   COTIZADOR CINTAC · lógica de la interfaz
   Los datos, la autenticación, los permisos y el cálculo viven en el servidor Django
   (endpoints /api/...). Este archivo solo dibuja la pantalla y llama a la API.
   ========================================================= */

/* Valores por defecto; los definitivos llegan desde /api/sesion/ */
let MAX_TON_CONT = 25;            // Decreto 75: máx. 25 t por contenedor
let MAX_INTENTOS = 3;             // intentos fallidos antes del bloqueo
let PERMISOS = {
  'Administrador': ['mod1','mod2','mod3','mod4'],
  'Analista':      ['mod1','mod2']
};
let RESTAURAR_USUARIOS = false;

let tarifas = [];
let usuarios = [];
let sesionActual = null;          // usuario con sesión iniciada
let usuarioPendiente = null;      // usuario que debe cambiar su clave antes de entrar
let ultimaCotizacion = null;
let simSeq = 0, cmpSeq = 0;       // descartan respuestas atrasadas del servidor

function aplicarConfig(c){
  if(!c) return;
  if(c.maxTonCont) MAX_TON_CONT = c.maxTonCont;
  if(c.maxIntentos) MAX_INTENTOS = c.maxIntentos;
  if(c.permisos) PERMISOS = c.permisos;
  RESTAURAR_USUARIOS = !!c.restaurarUsuariosHabilitado;
}

/* =========================================================
   UTILIDADES
   ========================================================= */
const $ = id => document.getElementById(id);
const nf0 = new Intl.NumberFormat('es-CL',{maximumFractionDigits:0});
const nf2 = new Intl.NumberFormat('es-CL',{minimumFractionDigits:2,maximumFractionDigits:2});
const nf1 = new Intl.NumberFormat('es-CL',{minimumFractionDigits:0,maximumFractionDigits:1});
const usd = v => 'US$ ' + nf2.format(v);
const clp = v => '$ ' + nf0.format(Math.round(v));
const num = id => { const v = parseFloat($(id).value); return isNaN(v) ? 0 : v; };
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const cobroLabel = c => c === 'contenedor' ? 'Por contenedor' : 'Por tonelada';
const clone = o => JSON.parse(JSON.stringify(o));

function toast(msg){
  const t = $('toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(toast._t); toast._t = setTimeout(()=>t.classList.remove('show'), 3200);
}

/* =========================================================
   COMUNICACIÓN CON EL SERVIDOR
   ========================================================= */
function leerCookie(nombre){
  const par = document.cookie.split('; ').find(c => c.startsWith(nombre + '='));
  return par ? decodeURIComponent(par.slice(nombre.length + 1)) : '';
}

/* opciones: {sinManejoSesion, silencioso}. Devuelve {ok, status, data} */
async function api(metodo, url, cuerpo, opciones){
  opciones = opciones || {};
  const init = {method:metodo, credentials:'same-origin', headers:{'Accept':'application/json'}};
  if(metodo !== 'GET'){
    init.headers['Content-Type'] = 'application/json';
    init.headers['X-CSRFToken'] = leerCookie('csrftoken');
    init.body = JSON.stringify(cuerpo || {});
  }
  let resp, data = {};
  try{
    resp = await fetch(url, init);
    try{ data = await resp.json(); }catch(e){ data = {}; }
  }catch(e){
    if(!opciones.silencioso) toast('No se pudo conectar con el servidor. Inténtalo nuevamente.');
    return {ok:false, status:0, data:{error:'No se pudo conectar con el servidor.'}};
  }
  if(!opciones.sinManejoSesion){
    if(resp.status === 401 && sesionActual){ sesionExpirada(); }
    else if(resp.status === 403 && data.codigo === 'solo_admin'){
      toast(data.error); if(sesionActual) mostrarModulo('mod1');
    }
  }
  return {ok:resp.ok, status:resp.status, data};
}

async function cargarTarifas(){
  const r = await api('GET', '/api/tarifas/');
  if(r.ok) tarifas = r.data.tarifas;
}
async function cargarUsuarios(){
  const r = await api('GET', '/api/usuarios/');
  if(r.ok) usuarios = r.data.usuarios;
}


/* =========================================================
   REGLAS DE CONTRASEÑA (el servidor las vuelve a validar)
   ========================================================= */
/* Reglas de complejidad obligatorias */
const REGLAS_CLAVE = [
  {id:'len',     txt:'Mínimo 8 caracteres',                         test:p => p.length >= 8},
  {id:'upper',   txt:'Al menos 1 letra mayúscula (A-Z)',            test:p => /[A-Z]/.test(p)},
  {id:'lower',   txt:'Al menos 1 letra minúscula (a-z)',            test:p => /[a-z]/.test(p)},
  {id:'digit',   txt:'Al menos 1 número (0-9)',                     test:p => /[0-9]/.test(p)},
  {id:'special', txt:'Al menos 1 carácter especial (!@#$%^&*)',     test:p => /[!@#$%^&*()_+\-=\[\]{};:'",.<>\/?\\|~`]/.test(p)}
];
function reglasIncumplidas(p){ return REGLAS_CLAVE.filter(r => !r.test(p)); }

/* =========================================================
   ROLES Y PERMISOS
   ========================================================= */
function puedeVer(mod){
  return !!sesionActual && (PERMISOS[sesionActual.rol] || []).includes(mod);
}
function esAdmin(){
  return !!sesionActual && sesionActual.rol === 'Administrador';
}
/* Protege las acciones de escritura de los mantenedores */
function requiereAdmin(){
  if(esAdmin()) return true;
  toast('Acción restringida: requiere rol Administrador.');
  mostrarModulo('mod1');
  return false;
}
function aplicarPermisosMenu(){
  document.querySelectorAll('nav button').forEach(b => { b.hidden = !puedeVer(b.dataset.mod); });
}
function renderSesion(){
  if(!sesionActual){ $('sessInfo').textContent = 'Sesión: —'; return; }
  $('sessInfo').innerHTML =
    `Sesión: <b>${esc(sesionActual.usuario)}</b> (${esc(sesionActual.rol)})` +
    `<span class="sess-name">${esc(sesionActual.nombre)}</span>`;
}

/* Cambio de módulo con redirección automática si no hay permiso */
function mostrarModulo(mod){
  if(!puedeVer(mod)){
    if(sesionActual && mod !== 'mod1') toast('Acceso restringido: te redirigimos al Simulador.');
    mod = 'mod1';
  }
  ['mod1','mod2','mod3','mod4'].forEach(m => $(m).hidden = (m !== mod));
  document.querySelectorAll('nav button').forEach(b => b.classList.toggle('active', b.dataset.mod === mod));
  if(mod !== 'mod4') ocultarTemporal();
  if(mod === 'mod2') renderComparador();
  if(mod === 'mod3') cargarTarifas().then(renderTodo);
  if(mod === 'mod4') cargarUsuarios().then(renderTablaUsuarios);
}

/* =========================================================
   LOGIN / INTENTOS FALLIDOS / PRIMER INGRESO (validados en el servidor)
   ========================================================= */
async function iniciarSesion(user){
  sesionActual = user;
  $('pwModal').hidden = true;
  $('login').hidden = true; $('app').hidden = false;
  if(!$('s_sol').value.trim()) $('s_sol').value = user.nombre;
  renderSesion();
  aplicarPermisosMenu();
  mostrarModulo('mod1');
  await refrescarTodo();
}

$('loginForm').addEventListener('submit', async e => {
  e.preventDefault();
  const err = $('loginError');
  const boton = $('loginForm').querySelector('button[type=submit]');
  const nombre = $('user').value.trim();
  const clave = $('pass').value;
  err.classList.remove('warn-attempts');

  if(!nombre || !clave){ err.textContent = 'Ingresa tu usuario y contraseña.'; return; }

  boton.disabled = true;
  const r = await api('POST', '/api/login/', {usuario:nombre, clave}, {sinManejoSesion:true});
  boton.disabled = false;
  $('pass').value = '';

  if(!r.ok){
    if(r.data.aviso) err.classList.add('warn-attempts');
    err.textContent = r.data.error || 'No fue posible iniciar sesión.';
    return;
  }
  err.textContent = '';
  if(r.data.requiereCambioClave){ abrirCambioClave({nombre:r.data.nombre}); return; }   // no entra al panel hasta cambiar la clave
  aplicarConfig(r.data.config);
  await iniciarSesion(r.data.usuario);
});

/* Limpia la interfaz y vuelve al login (sin llamar al servidor) */
function volverAlLogin(){
  sesionActual = null; usuarioPendiente = null;
  tarifas = []; usuarios = []; ultimaCotizacion = null;
  $('app').hidden = true; $('pwModal').hidden = true; $('login').hidden = false;
  $('pass').value = ''; $('user').value = ''; $('loginError').textContent = '';
  $('loginError').classList.remove('warn-attempts');
  $('s_sol').value = '';
  ocultarTemporal();
  aplicarPermisosMenu();
}
async function cerrarSesion(){
  await api('POST', '/api/logout/', {}, {sinManejoSesion:true, silencioso:true});
  volverAlLogin();
}
function sesionExpirada(){
  volverAlLogin();
  $('loginError').textContent = 'Tu sesión expiró. Ingresa nuevamente.';
}
$('btnLogout').addEventListener('click', cerrarSesion);

document.querySelectorAll('nav button').forEach(b =>
  b.addEventListener('click', () => mostrarModulo(b.dataset.mod)));

/* ---------- Modal de cambio obligatorio de contraseña ---------- */
function renderRequisitos(){
  const p = $('pw1').value, r = $('pw2').value;
  const items = REGLAS_CLAVE.map(x => ({txt:x.txt, ok:x.test(p)}));
  items.push({txt:'Las dos contraseñas coinciden', ok: r.length > 0 && p === r});
  $('pwReqs').innerHTML = items.map(i => `<li class="${i.ok?'ok':''}">${esc(i.txt)}</li>`).join('');
}
function abrirCambioClave(u){
  usuarioPendiente = u;
  $('pw1').value = ''; $('pw2').value = ''; $('pwError').textContent = '';
  $('pwIntro').textContent = `Hola, ${u.nombre}. Es tu primer ingreso: debes reemplazar la contraseña temporal por una propia para continuar.`;
  renderRequisitos();
  $('pwModal').hidden = false;
  setTimeout(() => $('pw1').focus(), 30);
}
['pw1','pw2'].forEach(id => $(id).addEventListener('input', () => { $('pwError').textContent = ''; renderRequisitos(); }));

$('pwForm').addEventListener('submit', async e => {
  e.preventDefault();
  if(!usuarioPendiente) return;
  const p1 = $('pw1').value, p2 = $('pw2').value, err = $('pwError');

  const faltan = reglasIncumplidas(p1);
  if(faltan.length){
    err.textContent = 'La contraseña no cumple el estándar. Falta: ' + faltan.map(f => f.txt.charAt(0).toLowerCase() + f.txt.slice(1)).join('; ') + '.';
    return;
  }
  if(p1 !== p2){ err.textContent = 'Las contraseñas no coinciden. Repítela exactamente igual.'; return; }

  const r = await api('POST', '/api/cambiar-clave/', {clave1:p1, clave2:p2}, {sinManejoSesion:true});
  if(!r.ok){
    err.textContent = r.data.error || 'No se pudo actualizar la contraseña.';
    if(r.data.expirada){ volverAlLogin(); $('loginError').textContent = r.data.error; }
    return;
  }
  usuarioPendiente = null;
  aplicarConfig(r.data.config);
  await iniciarSesion(r.data.usuario);
  toast('Contraseña actualizada correctamente.');
});

/* Cancelar: vuelve al login; la cuenta sigue con primer ingreso pendiente */
$('pwCancel').addEventListener('click', () => {
  usuarioPendiente = null;
  api('POST', '/api/cancelar-cambio-clave/', {}, {sinManejoSesion:true, silencioso:true});
  $('pwModal').hidden = true; $('pw1').value = ''; $('pw2').value = '';
  toast('Debes cambiar tu contraseña temporal para poder ingresar.');
});


/* =========================================================
   MÓDULO 1: SIMULADOR
   ========================================================= */
function poblarTarifasSim(){
  const sel = $('s_tarifa'), prev = sel.value;
  sel.innerHTML = tarifas.length ? tarifas.map(t =>
    `<option value="${t.id}">${esc(t.origen)} → ${esc(t.destino)} · ${esc(t.embarcador)} · US$ ${nf0.format(t.monto)}/${t.cobro==='contenedor'?'cont.':'ton'} · ${t.dias} días</option>`
  ).join('') : '<option value="">(Sin tarifas — un Administrador debe agregarlas)</option>';
  if(prev && tarifas.some(t => String(t.id) === prev)) sel.value = prev;
  else if(tarifas.length) $('s_dias').value = tarifas[0].dias;
}

function tarifaSeleccionada(){
  return tarifas.find(t => String(t.id) === $('s_tarifa').value);
}

function renderPeso(sug, cont, ton){
  const cap = cont * MAX_TON_CONT;
  const pct = cap > 0 ? (ton / cap) * 100 : 0;
  const excede = ton > cap && ton > 0;
  $('weightBox').innerHTML = `
    <div class="top">
      <div><small>CONTENEDORES SUGERIDOS</small><div class="big">${sug} <span style="font-size:13px;color:var(--muted);font-weight:normal">× ${MAX_TON_CONT} t máx.</span></div></div>
      <div style="text-align:right"><small>Carga / capacidad</small><div><b>${nf1.format(ton)} t</b> / ${nf1.format(cap)} t</div></div>
    </div>
    <div class="bar"><div class="${excede?'over':''}" style="width:${Math.min(pct,100)}%"></div></div>
    <small>Ocupación: ${nf1.format(pct)}% · Restricción legal Decreto 75 (máx. ${MAX_TON_CONT} t por contenedor)</small>`;
}

function calcSim(){
  const t = tarifaSeleccionada();
  const ton = num('s_ton');
  const sug = ton > 0 ? Math.ceil(ton / MAX_TON_CONT) : 0;
  const cont = num('s_cont') > 0 ? num('s_cont') : sug;
  renderPeso(sug, cont, ton);

  const box = $('simResult');
  if(!t || ton <= 0){
    ultimaCotizacion = null;
    $('cotTag').textContent = '—';
    box.innerHTML = '<div class="empty">Selecciona una tarifa e ingresa las toneladas para ver la cotización.</div>';
    return;
  }
  const seq = ++simSeq;
  clearTimeout(calcSim._t);
  calcSim._t = setTimeout(async () => {
    const r = await api('POST', '/api/cotizar/', {
      tarifaId:t.id, toneladas:ton, contenedores:num('s_cont'), fob:num('s_fob'),
      dias:num('s_dias'), tlc:$('s_tlc').checked, tc:num('s_tc') || 1});
    if(seq !== simSeq) return;                       // llegó una respuesta más nueva
    if(!r.ok){
      ultimaCotizacion = null;
      $('cotTag').textContent = '—';
      box.innerHTML = `<div class="empty">${esc(r.data.error || 'No se pudo calcular la cotización.')}</div>`;
      return;
    }
    pintarCotizacion(t, r.data.resultado);
  }, 150);
}

/* Muestra el resultado calculado por el servidor */
function pintarCotizacion(t, resultado){
  const box = $('simResult');
  const r = {tarifa:t, ...resultado};
  ultimaCotizacion = {
    ...r,
    ref: $('s_ref').value.trim(), sol: $('s_sol').value.trim(),
    numero: ultimaCotizacion && ultimaCotizacion.numero ? ultimaCotizacion.numero : generarNumero()
  };
  $('cotTag').textContent = ultimaCotizacion.numero;

  const exceso = r.tonPorCont > MAX_TON_CONT;
  const cantTxt = t.cobro === 'contenedor' ? `${r.contUsados} contenedor(es)` : `${nf1.format(r.toneladas)} t`;
  const aranTxt = r.tlc ? 'Arancel (TLC 0%)' : `Arancel (${nf1.format(r.pctArancel*100)}% s/CIF)`;

  box.innerHTML = `
    ${exceso ? `<div class="alert warn">⚠ Con ${r.contUsados} contenedor(es) la carga supera el máximo legal de ${MAX_TON_CONT} t por contenedor (${nf1.format(r.tonPorCont)} t/cont.). Se sugieren <b>${r.sugeridos}</b>.</div>` : ''}
    <div class="kpis">
      <div class="kpi active"><span>Costo total importación (CLP)</span><b>${clp(r.totalCLP)}</b></div>
      <div class="kpi"><span>Costo total importación (USD)</span><b>${usd(r.totalUSD)}</b></div>
    </div>
    <div class="table-wrap"><table>
      <thead><tr><th>Concepto</th><th class="num">USD</th><th class="num">CLP</th></tr></thead>
      <tbody>
        <tr><td>Valor FOB</td><td class="num">${usd(r.fob)}</td><td class="num">${clp(r.fob*r.tc)}</td></tr>
        <tr><td>Flete base<br><small style="color:var(--muted)">US$ ${nf2.format(t.monto)} × ${cantTxt}</small></td><td class="num">${usd(r.fleteBase)}</td><td class="num">${clp(r.fleteBase*r.tc)}</td></tr>
        <tr><td>Contingencia logística (+${nf1.format(r.pctCont*100)}%)<br><small style="color:var(--muted)">${r.dias} días de tránsito</small></td><td class="num">${usd(r.recargo)}</td><td class="num">${clp(r.recargo*r.tc)}</td></tr>
        <tr class="sub"><td>Flete total con margen</td><td class="num">${usd(r.fleteTotal)}</td><td class="num">${clp(r.fleteTotal*r.tc)}</td></tr>
        <tr><td>Seguro <small style="color:var(--muted)">(exento, póliza global CINTAC)</small></td><td class="num">${usd(0)}</td><td class="num">${clp(0)}</td></tr>
        <tr class="sub"><td>Valor CIF</td><td class="num">${usd(r.cif)}</td><td class="num">${clp(r.cif*r.tc)}</td></tr>
        <tr><td>${aranTxt}</td><td class="num">${usd(r.arancel)}</td><td class="num">${clp(r.arancel*r.tc)}</td></tr>
        <tr><td>IVA (19% s/CIF)</td><td class="num">${usd(r.iva)}</td><td class="num">${clp(r.iva*r.tc)}</td></tr>
        <tr class="total"><td>TOTAL</td><td class="num">${usd(r.totalUSD)}</td><td class="num">${clp(r.totalCLP)}</td></tr>
      </tbody>
    </table></div>
    <div class="actions">
      <button class="btn btn-primary" id="btnPrint">🖨 Exportar / Imprimir cotización</button>
    </div>`;
  $('btnPrint').addEventListener('click', imprimirCotizacion);
}

function generarNumero(){
  const d = new Date();
  const p = n => String(n).padStart(2,'0');
  return `COT-${d.getFullYear()}${p(d.getMonth()+1)}${p(d.getDate())}-${String(Math.floor(Math.random()*9000)+1000)}`;
}

/* Referencia y solicitante no requieren recalcular: solo se actualizan en la cotización vigente */
['s_ref','s_sol'].forEach(id => $(id).addEventListener('input', () => {
  if(ultimaCotizacion){ ultimaCotizacion.ref = $('s_ref').value.trim(); ultimaCotizacion.sol = $('s_sol').value.trim(); }
}));
['s_fob','s_dias','s_tc','s_cont'].forEach(id => $(id).addEventListener('input', calcSim));
$('s_ton').addEventListener('input', () => {
  const ton = num('s_ton');
  $('s_cont').value = ton > 0 ? Math.ceil(ton / MAX_TON_CONT) : '';
  calcSim();
});
$('s_tlc').addEventListener('change', calcSim);
$('s_tarifa').addEventListener('change', () => {
  const t = tarifaSeleccionada();
  if(t) $('s_dias').value = t.dias;
  calcSim();
});

/* ---------- Impresión ---------- */
function imprimirCotizacion(){
  const q = ultimaCotizacion; if(!q) return;
  const t = q.tarifa;
  const fecha = new Date().toLocaleDateString('es-CL',{day:'2-digit',month:'long',year:'numeric'});
  const cantTxt = t.cobro === 'contenedor' ? `${q.contUsados} contenedor(es)` : `${nf1.format(q.toneladas)} t`;
  const elabora = sesionActual ? `${esc(sesionActual.nombre)} (${esc(sesionActual.usuario)})` : 'Elaborado por';
  $('printArea').innerHTML = `
    <div class="pr-head">
      <div class="brand">CINTAC<small>Gerencia de Abastecimiento · COMEX</small></div>
      <div class="meta">Cotización interna de flete de importación<br><b>${esc(q.numero)}</b><br>${fecha}</div>
    </div>
    <h2>Detalle de cotización</h2>
    <h3>Datos de la operación</h3>
    <div class="pr-kv">
      <div><span>Referencia</span><b>${esc(q.ref || '—')}</b></div>
      <div><span>Solicitante</span><b>${esc(q.sol || '—')}</b></div>
      <div><span>Ruta</span><b>${esc(t.origen)} → ${esc(t.destino)}</b></div>
      <div><span>Embarcador</span><b>${esc(t.embarcador)}</b></div>
      <div><span>Carga</span><b>${nf1.format(q.toneladas)} t</b></div>
      <div><span>Contenedores</span><b>${q.contUsados} (${nf1.format(q.tonPorCont)} t/cont.)</b></div>
      <div><span>Tránsito</span><b>${q.dias} días</b></div>
      <div><span>Régimen</span><b>${q.tlc ? 'Acogido a TLC' : 'Sin TLC'}</b></div>
      <div><span>Tarifa</span><b>US$ ${nf2.format(t.monto)} / ${t.cobro==='contenedor'?'contenedor':'tonelada'}</b></div>
      <div><span>Tipo de cambio</span><b>$ ${nf2.format(q.tc)} / USD</b></div>
    </div>
    <h3>Desglose de costos</h3>
    <table>
      <thead><tr><th>Concepto</th><th class="num">USD</th><th class="num">CLP</th></tr></thead>
      <tbody>
        <tr><td>Valor FOB</td><td class="num">${usd(q.fob)}</td><td class="num">${clp(q.fob*q.tc)}</td></tr>
        <tr><td>Flete base (${cantTxt})</td><td class="num">${usd(q.fleteBase)}</td><td class="num">${clp(q.fleteBase*q.tc)}</td></tr>
        <tr><td>Contingencia logística (+${nf1.format(q.pctCont*100)}%)</td><td class="num">${usd(q.recargo)}</td><td class="num">${clp(q.recargo*q.tc)}</td></tr>
        <tr class="sub"><td>Flete total con margen</td><td class="num">${usd(q.fleteTotal)}</td><td class="num">${clp(q.fleteTotal*q.tc)}</td></tr>
        <tr><td>Seguro (exento póliza global)</td><td class="num">${usd(0)}</td><td class="num">${clp(0)}</td></tr>
        <tr class="sub"><td>Valor CIF</td><td class="num">${usd(q.cif)}</td><td class="num">${clp(q.cif*q.tc)}</td></tr>
        <tr><td>${q.tlc ? 'Arancel (TLC 0%)' : 'Arancel (6% s/CIF)'}</td><td class="num">${usd(q.arancel)}</td><td class="num">${clp(q.arancel*q.tc)}</td></tr>
        <tr><td>IVA (19% s/CIF)</td><td class="num">${usd(q.iva)}</td><td class="num">${clp(q.iva*q.tc)}</td></tr>
        <tr class="total"><td>TOTAL COSTO DE IMPORTACIÓN</td><td class="num">${usd(q.totalUSD)}</td><td class="num">${clp(q.totalCLP)}</td></tr>
      </tbody>
    </table>
    <ul class="pr-notes">
      <li>Restricción legal de carga: máximo ${MAX_TON_CONT} toneladas por contenedor (Decreto 75).</li>
      <li>Seguro exento por póliza global CINTAC. IVA calculado sobre valor CIF.</li>
      <li>Las tarifas son referenciales y sujetas a confirmación del embarcador. Documento de uso interno.</li>
    </ul>
    <div class="pr-sign"><div>Elaborado por<br>${elabora}</div><div>V°B° Jefatura COMEX</div></div>`;
  window.print();
}

/* =========================================================
   MÓDULO 2: COMPARADOR
   ========================================================= */
function poblarRutas(){
  const sel = $('c_ruta'), prev = sel.value;
  const rutas = [...new Set(tarifas.map(t => `${t.origen} → ${t.destino}`))];
  sel.innerHTML = rutas.length ? rutas.map(r => `<option value="${esc(r)}">${esc(r)}</option>`).join('')
                               : '<option value="">(Sin rutas)</option>';
  if(prev && rutas.includes(prev)) sel.value = prev;
}

function renderComparador(){
  const box = $('cmpResult');
  const ruta = $('c_ruta').value, ton = num('c_ton');
  const lista = tarifas.filter(t => `${t.origen} → ${t.destino}` === ruta);
  const seq = ++cmpSeq;
  clearTimeout(renderComparador._t);
  if(!lista.length || ton <= 0){
    box.innerHTML = '<div class="card empty" style="margin-top:20px">Selecciona una ruta e ingresa las toneladas para comparar.</div>'; return;
  }
  renderComparador._t = setTimeout(async () => {
    const r = await api('POST', '/api/comparar/', {
      ruta, toneladas:ton, fob:num('c_fob'), tc:num('c_tc') || 1, tlc:$('c_tlc').checked});
    if(seq !== cmpSeq) return;                       // llegó una respuesta más nueva
    if(!r.ok){
      box.innerHTML = `<div class="card empty" style="margin-top:20px">${esc(r.data.error || 'No se pudo comparar.')}</div>`;
      return;
    }
    pintarComparador(r.data.resultados);
  }, 150);
}

/* res: resultados del servidor, ya ordenados del más barato al más caro */
function pintarComparador(res){
  const box = $('cmpResult');
  const masRapido = Math.min(...res.map(r => r.dias));
  const mejor = res[0], peor = res[res.length-1];
  const ahorroUSD = peor.totalUSD - mejor.totalUSD;

  box.innerHTML = `
    <div class="cmp-grid">
      ${res.map((r,i) => `
        <div class="cmp-card ${i===0?'best':''}">
          ${i===0 ? '<span class="badge">★ MÁS CONVENIENTE</span>' : ''}
          ${r.dias === masRapido ? '<span class="badge alt">⚡ MÁS RÁPIDO</span>' : ''}
          <h4>${esc(r.tarifa.embarcador)}</h4>
          <div class="route">${esc(r.tarifa.origen)} → ${esc(r.tarifa.destino)} · ${cobroLabel(r.tarifa.cobro)}</div>
          <div class="total">${usd(r.totalUSD)}</div>
          <div class="total-clp">${clp(r.totalCLP)}</div>
          <dl>
            <dt>Tarifa</dt><dd>US$ ${nf2.format(r.tarifa.monto)}</dd>
            <dt>Flete base</dt><dd>${usd(r.fleteBase)}</dd>
            <dt>Contingencia (+${nf1.format(r.pctCont*100)}%)</dt><dd>${usd(r.recargo)}</dd>
            <dt>Flete con margen</dt><dd>${usd(r.fleteTotal)}</dd>
            <dt>Valor CIF</dt><dd>${usd(r.cif)}</dd>
            <dt>Arancel + IVA</dt><dd>${usd(r.arancel + r.iva)}</dd>
            <dt>Tránsito</dt><dd>${r.dias} días</dd>
            <dt>Contenedores</dt><dd>${r.contUsados}</dd>
          </dl>
        </div>`).join('')}
    </div>
    ${res.length > 1 ? `<div class="save-box">La opción más conveniente es <b>${esc(mejor.tarifa.embarcador)}</b>: ahorra
      <b>${usd(ahorroUSD)}</b> (${clp(ahorroUSD*mejor.tc)}) frente a la alternativa más cara (${esc(peor.tarifa.embarcador)}).
      Considera el tránsito: la contingencia logística aumenta con los días de viaje.</div>` : ''}`;
}
['c_ruta','c_ton','c_fob','c_tc'].forEach(id => $(id).addEventListener('input', renderComparador));
$('c_tlc').addEventListener('change', renderComparador);

/* =========================================================
   MÓDULO 3: MANTENEDOR DE TARIFAS (solo Administrador)
   ========================================================= */
function renderTablaTarifas(){
  $('tarifaCount').textContent = tarifas.length;
  $('tarifaBody').innerHTML = tarifas.length ? tarifas.map(t => `
    <tr>
      <td><b>${esc(t.embarcador)}</b></td><td>${esc(t.origen)}</td><td>${esc(t.destino)}</td>
      <td>${cobroLabel(t.cobro)}</td><td class="num">${usd(t.monto)}</td><td class="num">${t.dias} días</td>
      <td class="acciones"><button class="btn btn-danger" data-del="${t.id}">Eliminar</button></td>
    </tr>`).join('') : '<tr><td colspan="7" class="empty">No hay tarifas registradas.</td></tr>';
  document.querySelectorAll('[data-del]').forEach(b => b.addEventListener('click', async () => {
    if(!requiereAdmin()) return;
    const r = await api('DELETE', `/api/tarifas/${Number(b.dataset.del)}/`);
    if(!r.ok){ toast(r.data.error || 'No se pudo eliminar la tarifa.'); return; }
    tarifas = r.data.tarifas; renderTodo(); toast('Tarifa eliminada');
  }));
}

$('btnAddTarifa').addEventListener('click', async () => {
  if(!requiereAdmin()) return;
  const emb = $('t_emb').value.trim(), ori = $('t_ori').value.trim(), des = $('t_des').value.trim();
  const monto = parseFloat($('t_monto').value), dias = parseInt($('t_dias').value, 10);
  if(!emb || !ori || !des || !(monto > 0) || !(dias > 0)){
    $('tarifaError').textContent = 'Completa todos los campos con valores válidos (tarifa y días mayores a 0).'; return;
  }
  $('tarifaError').textContent = '';
  const r = await api('POST', '/api/tarifas/', {embarcador:emb, origen:ori, destino:des, cobro:$('t_cobro').value, monto, dias});
  if(!r.ok){ $('tarifaError').textContent = r.data.error || 'No se pudo agregar la tarifa.'; return; }
  tarifas = r.data.tarifas; renderTodo();
  ['t_emb','t_ori','t_des','t_monto','t_dias'].forEach(i => $(i).value = '');
  toast('Tarifa agregada');
});
$('btnReset').addEventListener('click', async () => {
  if(!requiereAdmin()) return;
  if(!confirm('¿Restaurar las tarifas de ejemplo? Se perderán los cambios actuales.')) return;
  const r = await api('POST', '/api/tarifas/restaurar/');
  if(!r.ok){ toast(r.data.error || 'No se pudo restaurar las tarifas.'); return; }
  tarifas = r.data.tarifas; renderTodo(); toast('Tarifas restauradas');
});

/* =========================================================
   MÓDULO 4: GESTIÓN DE USUARIOS (solo Administrador)
   ========================================================= */
function totalAdmins(){ return usuarios.filter(u => u.rol === 'Administrador').length; }

/* Aviso con la contraseña temporal (solo se muestra una vez; no se guarda en texto plano) */
function mostrarTemporal(usuario, clave, motivo){
  const box = $('tempBox');
  box.innerHTML = `
    <div>
      <b>${esc(motivo)}</b> para <b>${esc(usuario)}</b><br>
      <code>${esc(clave)}</code><br>
      <small>Entrégala al usuario por un canal seguro. Deberá cambiarla en su primer ingreso. Esta clave no se volverá a mostrar.</small>
    </div>
    <button class="btn btn-outline btn-sm" id="btnCerrarTemp">Entendido</button>`;
  box.hidden = false;
  $('btnCerrarTemp').addEventListener('click', ocultarTemporal);
}
function ocultarTemporal(){
  const box = $('tempBox'); if(!box) return;
  box.hidden = true; box.innerHTML = '';
}

/* Varias contraseñas temporales a la vez (restauración de usuarios de ejemplo) */
function mostrarTemporales(lista, motivo){
  const box = $('tempBox');
  box.innerHTML = `
    <div>
      <b>${esc(motivo)}</b><br>
      ${lista.map(t => `<b>${esc(t.usuario)}</b> <code>${esc(t.clave)}</code><br>`).join('')}
      <small>Entrégalas a cada usuario por un canal seguro. Deberán cambiarlas en su primer ingreso. Estas claves no se volverán a mostrar.</small>
    </div>
    <button class="btn btn-outline btn-sm" id="btnCerrarTemp">Entendido</button>`;
  box.hidden = false;
  $('btnCerrarTemp').addEventListener('click', ocultarTemporal);
}

function renderTablaUsuarios(){
  $('userCount').textContent = usuarios.length;
  $('userBody').innerHTML = usuarios.length ? usuarios.map(u => {
    const yo = sesionActual && sesionActual.id === u.id;
    const bloqueado = u.estado === 'Bloqueado';
    return `
    <tr>
      <td><b>${esc(u.nombre)}</b>${yo ? '<span class="you">(tú)</span>' : ''}</td>
      <td>${esc(u.usuario)}</td>
      <td><span class="pill ${u.rol==='Administrador'?'rol-admin':'rol-analista'}">${esc(u.rol)}</span></td>
      <td><span class="pill ${bloqueado?'est-bloqueado':'est-activo'}">${esc(u.estado)}</span>
        ${u.intentosFallidos > 0 && !bloqueado ? `<small class="sub-info">${u.intentosFallidos}/${MAX_INTENTOS} intentos fallidos</small>` : ''}</td>
      <td><span class="pill ${u.primerIngreso?'clave-temp':'clave-ok'}">${u.primerIngreso ? 'Temporal (pendiente de cambio)' : 'Definitiva'}</span></td>
      <td class="acciones">
        ${bloqueado ? `<button class="btn btn-outline btn-sm" data-act="unlock" data-id="${u.id}">Desbloquear</button>` : ''}
        ${yo ? '' : `<button class="btn btn-outline btn-sm" data-act="reset" data-id="${u.id}">Restablecer clave</button>`}
        <button class="btn btn-danger" data-act="del" data-id="${u.id}">Eliminar</button>
      </td>
    </tr>`;
  }).join('') : '<tr><td colspan="6" class="empty">No hay usuarios registrados.</td></tr>';
}

/* Un solo listener para las acciones de la tabla */
$('userBody').addEventListener('click', e => {
  const b = e.target.closest('button[data-act]'); if(!b) return;
  const id = Number(b.dataset.id);
  if(b.dataset.act === 'unlock') desbloquearUsuario(id);
  else if(b.dataset.act === 'reset') restablecerClave(id);
  else if(b.dataset.act === 'del') eliminarUsuario(id);
});

async function desbloquearUsuario(id){
  if(!requiereAdmin()) return;
  const r = await api('POST', `/api/usuarios/${id}/desbloquear/`);
  if(!r.ok){ toast(r.data.error || 'No se pudo desbloquear al usuario.'); return; }
  usuarios = r.data.usuarios; renderTablaUsuarios(); toast(r.data.mensaje);
}

async function restablecerClave(id){
  if(!requiereAdmin()) return;
  const u = usuarios.find(x => x.id === id); if(!u) return;
  if(sesionActual && u.id === sesionActual.id){ toast('No puedes restablecer tu propia clave con la sesión activa.'); return; }
  if(!confirm(`¿Generar una nueva contraseña temporal para "${u.usuario}"?`)) return;
  const r = await api('POST', `/api/usuarios/${id}/restablecer/`);
  if(!r.ok){ toast(r.data.error || 'No se pudo restablecer la clave.'); return; }
  usuarios = r.data.usuarios; renderTablaUsuarios();
  mostrarTemporal(r.data.temporal.usuario, r.data.temporal.clave, 'Nueva contraseña temporal');
}

async function eliminarUsuario(id){
  if(!requiereAdmin()) return;
  const u = usuarios.find(x => x.id === id); if(!u) return;
  if(sesionActual && u.id === sesionActual.id){ toast('No puedes eliminar tu propio usuario con la sesión activa.'); return; }
  if(u.rol === 'Administrador' && totalAdmins() <= 1){
    toast('Debe existir al menos un Administrador.'); return;
  }
  if(!confirm(`¿Eliminar al usuario "${u.usuario}"?`)) return;
  const r = await api('DELETE', `/api/usuarios/${id}/`);
  if(!r.ok){ toast(r.data.error || 'No se pudo eliminar al usuario.'); return; }
  usuarios = r.data.usuarios; renderTablaUsuarios(); toast('Usuario eliminado');
}

$('btnAddUser').addEventListener('click', async () => {
  if(!requiereAdmin()) return;
  const nombre = $('u_nombre').value.trim();
  const usuario = $('u_user').value.trim();
  const rol = $('u_rol').value;
  const err = $('userError');

  if(!nombre || !usuario){ err.textContent = 'Completa el nombre completo y el correo / usuario.'; return; }
  if(/\s/.test(usuario)){ err.textContent = 'El correo / usuario no puede contener espacios.'; return; }
  if(usuario.includes('@') && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(usuario)){
    err.textContent = 'El correo ingresado no tiene un formato válido.'; return;
  }
  if(!PERMISOS[rol]){ err.textContent = 'Selecciona un rol válido.'; return; }
  if(usuarios.some(u => u.usuario.toLowerCase() === usuario.toLowerCase())){
    err.textContent = `El usuario "${usuario}" ya existe.`; return;
  }
  err.textContent = '';

  const r = await api('POST', '/api/usuarios/', {nombre, usuario, rol});
  if(!r.ok){ err.textContent = r.data.error || 'No se pudo crear el usuario.'; return; }
  usuarios = r.data.usuarios; renderTablaUsuarios();
  ['u_nombre','u_user'].forEach(i => $(i).value = '');
  $('u_rol').value = 'Analista';
  mostrarTemporal(r.data.temporal.usuario, r.data.temporal.clave, 'Usuario creado. Contraseña temporal');
});

$('btnResetUsers').addEventListener('click', async () => {
  if(!requiereAdmin()) return;
  if(!confirm('¿Restaurar los usuarios de ejemplo? Se perderán los usuarios creados y sus contraseñas.')) return;
  const r = await api('POST', '/api/usuarios/restaurar/');
  if(!r.ok){ toast(r.data.error || 'No se pudo restaurar a los usuarios.'); return; }
  usuarios = r.data.usuarios; renderTablaUsuarios();
  mostrarTemporales(r.data.temporales || [], 'Usuarios de ejemplo restaurados. Contraseñas temporales');
  toast('Usuarios restaurados');
});

/* =========================================================
   INICIO
   ========================================================= */
function renderTodo(){
  renderTablaTarifas(); poblarTarifasSim(); poblarRutas(); calcSim(); renderComparador();
  if(esAdmin()) renderTablaUsuarios();
}
async function refrescarTodo(){
  await cargarTarifas();
  if(esAdmin()) await cargarUsuarios();
  renderTodo();
}

$('s_cont').value = Math.ceil(num('s_ton') / MAX_TON_CONT);

/* Restaurar sesión si el navegador conserva una sesión vigente en el servidor */
(async function restaurarSesion(){
  const r = await api('GET', '/api/sesion/', null, {sinManejoSesion:true, silencioso:true});
  if(!r.ok) return;
  aplicarConfig(r.data.config);
  if(r.data.autenticado) await iniciarSesion(r.data.usuario);
})();
