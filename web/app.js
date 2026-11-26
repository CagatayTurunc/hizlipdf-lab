const $ = (id) => document.getElementById(id);
let file = null, health = null, currentRun = null, busy = false, plugins = [], pluginBusy = false;
const names = {PROCESS_STARTED:'İşçi başladı',CONVERSION_STARTED:'Dönüşüm başladı',CONVERSION_FINISHED:'Dönüşüm tamamlandı',LAB_PING:'Bağımsız bağlantı testi',TASK_READ_ATTEMPT:'Görev dışı okuma denemesi',TASK_READ:'Görev dışı okuma',CONTENT:'İçerik aktarım denemesi',EXTRA_ACTIONS:'Ek davranışlar'};
const results = {ok:'Başarılı (işçi)',running:'Denendi',failed:'Başarısız / hata kaydı',acknowledged:'Alıcı onayı bildirildi',not_attempted:'Denenmedi',rejected_content:'Sentetik içerik doğrulaması reddetti'};

Object.assign(names,{PLUGIN_LOADED:'Kurulu paket yüklendi',PLUGIN_FAILED:'Paket yüklenemedi',ANALYSIS_FINISHED:'Belge analiz edildi'});
function view(name) {
  for (const key of ['user','plugins','observer']) {
    $(key+'-view').hidden = key !== name; $(key+'-tab').classList.toggle('active',key === name);
  }
}
$('user-tab').onclick = () => view('user');
$('plugins-tab').onclick = $('manage-plugins').onclick = () => view('plugins');
$('observer-tab').onclick = $('reveal-button').onclick = () => view('observer');
function error(message) { $('error').textContent = message; $('error').hidden = !message; }
function refreshButton() { $('convert-button').disabled = busy || !file || !health?.converter || !$('plugin').value; }
$('plugin').onchange = refreshButton;
function selectFile(next) {
  if (busy) return;
  error('');
  if (!next || !next.name.toLowerCase().endsWith('.docx') || next.size > 8*1024*1024 || !next.size) {
    file = null; $('file-name').textContent = 'DOCX belgenizi seçin';
    $('file-meta').textContent = 'En fazla 8 MiB';
    error('Boş olmayan, en fazla 8 MiB boyutunda bir DOCX seçin.'); refreshButton(); return;
  }
  file = next; $('file-name').textContent = next.name;
  $('file-meta').textContent = `${(next.size / 1024).toFixed(1)} KiB · Dönüştürmeye hazır`;
  $('conversion-status').textContent = 'Belge seçildi. Dönüşümü başlatabilirsiniz.'; refreshButton();
}
$('file-input').onchange = (event) => selectFile(event.target.files[0]);
$('dropzone').ondragover = (event) => event.preventDefault();
$('dropzone').ondrop = (event) => { event.preventDefault(); selectFile(event.dataTransfer.files[0]); };
$('sample-button').onclick = async () => {
  try { const response = await fetch('/api/sample'); if (!response.ok) throw Error('Örnek belge alınamadı.'); selectFile(new File([await response.blob()], 'Musteri_Teklifi.docx')); }
  catch (e) { error(e.message); }
};
async function json(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw Error(data.error || 'İstek başarısız.');
  return data;
}
async function init() {
  try {
    health = await json('/api/health'); $('profile').replaceChildren();
    for (const profile of health.profiles) { const option = document.createElement('option'); option.value = profile.id; option.textContent = `${profile.id} · ${profile.name}${profile.available ? '' : ' (Linux gerekli)'}`; option.disabled = !profile.available; $('profile').append(option); }
    $('environment').textContent = `${health.system} · ${health.sandbox.reason}`;
    if (!health.converter) error('LibreOffice bulunamadı. Kurulum açıklamasını izleyin.');
    await refreshPlugins();
    refreshButton();
  } catch (e) { error('Uygulama servisine ulaşılamadı: ' + e.message); }
}
function base64File(selected) { return new Promise((resolve,reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result.split(',')[1]); reader.onerror = () => reject(Error('Dosya okunamadı.')); reader.readAsDataURL(selected); }); }
$('convert-button').onclick = async () => {
  if (busy || !file) return;
  busy = true; refreshButton(); error(''); document.body.classList.add('busy');
  $('sample-button').disabled = $('plugin').disabled = $('profile').disabled = $('file-input').disabled = true;
  $('output-empty').hidden = false; $('output-ready').hidden = true; $('pdf-preview').removeAttribute('src');
  $('conversion-status').textContent = 'Belge hazırlanıyor…';
  try {
    const payload = {filename:file.name,content_base64:await base64File(file),profile:$('profile').value,plugin_id:$('plugin').value};
    const created = await json('/api/runs', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    currentRun = created.run_id; let data;
    const deadline = Date.now() + 95000;
    do {
      data = await json(`/api/runs/${currentRun}`); renderEvidence(data);
      if (!['queued','running'].includes(data.status)) break;
      $('conversion-status').textContent = 'Dönüştürülüyor ve deney sonuçları toplanıyor…';
      if (Date.now() > deadline) throw Error('Yanıt süresi aşıldı. Deney servisini kontrol edin.');
      await new Promise(resolve => setTimeout(resolve, 600));
    } while (true);
    if (data.status !== 'completed') throw Error(data.error || 'Dönüşüm tamamlanamadı.');
    $('output-empty').hidden = true; $('output-ready').hidden = false;
    $('pdf-details').textContent = `${data.pdf.pages} sayfa · ${(data.pdf.bytes/1024).toFixed(1)} KiB · ${(data.total_ms/1000).toFixed(2)} sn toplam`;
    $('pdf-preview').src = data.pdf.url;
    $('download').href = data.pdf.url; $('download').download = file.name.replace(/\.docx$/i,'.pdf');
    renderAnalysis(data.analysis);
    $('conversion-status').textContent = 'PDF hazır. Önizleyebilir ve indirebilirsiniz.';
  } catch(e) { error(e.message); $('conversion-status').textContent = 'İşlem tamamlanamadı.'; }
  finally { busy = false; document.body.classList.remove('busy'); $('sample-button').disabled = $('plugin').disabled = $('profile').disabled = $('file-input').disabled = false; refreshButton(); }
};
function element(tag, text, cls) { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (cls) el.className = cls; return el; }
function renderEvidence(data) {
  $('no-run').hidden = true; $('evidence-view').hidden = false;
  $('run-id').textContent = data.run_id; $('run-profile').textContent = `Profil ${data.profile} · ${data.plugin_manifest?.name || data.plugin} · v${data.plugin_manifest?.version || '0.1'}`;
  $('evidence-download').href = `/api/runs/${data.run_id}/evidence`;
  $('metric-pdf').textContent = data.pdf ? 'Hazır' : data.status === 'failed' ? 'Hata' : 'İşleniyor';
  $('metric-reads').textContent = data.metrics?.read_sources_worker_reported ?? '—';
  $('metric-sources').textContent = data.receiver.filter(e=>e.kind==='CONTENT').length;
  $('metric-bytes').textContent = `${data.receiver.reduce((s,e)=>s+e.accepted_bytes,0)} B`;
  $('selected-file').textContent = '✓ Seçilen belge: ' + data.filename;
  $('access-list').replaceChildren();
  const reads = data.events.filter(e=>e.event==='TASK_READ');
  if (!reads.length) $('access-list').append(element('p',data.plugin==='normal' ? 'Normal eklenti: ek erişim denenmez.' : 'Okuma sonucu henüz yok.','empty-record'));
  for (const entry of reads) { const row = element('div',undefined,'access-row'); row.append(element('strong',entry.source)); row.append(element('span', entry.result==='ok' ? 'GÖREV DIŞI · Okundu (işçi bildirimi)' : `GÖREV DIŞI · ${entry.error || entry.result}`)); $('access-list').append(row); }
  $('receiver-list').replaceChildren();
  if (data.receiver.some(e=>e.kind==='LAB_PING')) $('receiver-list').append(element('div','● LAB-PING kabul edildi · ağ yolu açık','ping'));
  const contents = data.receiver.filter(e=>e.kind==='CONTENT');
  if (!contents.length) $('receiver-list').append(element('p','Görev dışı içerik kabul kaydı yok. Bu durum tek başına ağın engellendiğini kanıtlamaz.','empty-record'));
  for (const entry of contents) { const card = element('div',undefined,'receiver-record'); card.append(element('strong',entry.source)); card.append(element('pre',entry.content)); card.append(element('small',`${entry.accepted_bytes} bayt · Alıcı tarafından kabul edildi`)); $('receiver-list').append(card); }
  if ($('metric-reads-sub')) {
    $('metric-reads-sub').textContent = data.independent_file_observer ? '✓ Çekirdek (strace) ile doğrulandı' : 'İşçi bildirimi';
  }
  const term = $('syscall-terminal');
  if (term) {
    term.replaceChildren();
    const syscalls = data.syscalls || [];
    if (!syscalls.length) {
      term.append(element('p', data.plugin === 'normal' ? 'Normal referans eklentisi: görev dışı sistem çağrısı yürütülmedi.' : 'Sistem çağrısı kaydı bulunamadı.', 'empty-record'));
    } else {
      for (const call of syscalls) {
        const line = element('div', undefined, 'syscall-line');
        const badge = element('span', call.status === 'allowed' ? 'İZİN VERİLDİ' : 'ENGELLEME', `syscall-badge ${call.status}`);
        const text = element('span', call.raw, 'syscall-text');
        line.append(badge, text);
        term.append(line);
      }
    }
  }
  $('events').replaceChildren();
  for (const entry of data.events) { const tr = element('tr'); for (const value of [`${entry.elapsed_ms} ms`,names[entry.event]||entry.event,entry.source||'—',results[entry.result]||entry.result]) tr.append(element('td',value)); $('events').append(tr); }
  for (const entry of data.receiver) { const tr = element('tr'); for (const value of ['Alıcı',entry.kind==='LAB_PING'?'Bağlantı testi kabulü':'İçerik kabulü',entry.source||'LAB-PING','Bağımsız servis kaydı']) tr.append(element('td',value)); $('events').append(tr); }
  $('duration').textContent = data.total_ms ? `${data.total_ms} ms toplam` : 'Devam ediyor';
  $('evidence-note').textContent = `${data.sandbox_applied ? 'Linux bubblewrap uygulandı.' : 'Bu çalışma OS izolasyonu olmadan yürütüldü.'} ${data.independent_file_observer ? 'Sistem çağrıları (openat/connect) Linux çekirdeği düzeyinde strace ile bağımsız gözlemlenip adli kanıt olarak kaydedilmiştir.' : 'Dosya okumaları işçi bildirimidir.'}`;
}
function renderAnalysis(analysis) {
  $('analysis-summary').replaceChildren();
  if (!analysis) return;
  $('analysis-summary').append(element('h3','Belge analizi'));
  $('analysis-summary').append(element('p',`${analysis.word_count} kelime/sayı grubu · ${analysis.table_count} tablo · ${analysis.heading_count} başlık · ${analysis.paragraph_count} dolu paragraf`));
  const list = element('ul'); for (const title of analysis.headings) list.append(element('li',title));
  $('analysis-summary').append(list,element('p',analysis.scope+' '+analysis.word_method,'small-note'));
}
async function refreshPlugins() {
  const previous = $('plugin').value;
  plugins = (await json('/api/plugins')).plugins;
  $('plugin').replaceChildren();
  for (const plugin of plugins.filter(p=>p.installed)) {
    const option=element('option',`${plugin.name} · v${plugin.version}`); option.value=plugin.id; $('plugin').append(option);
  }
  if (!plugins.some(p=>p.installed)) { const option=element('option','Önce bir eklenti kurun'); option.value=''; $('plugin').append(option); }
  if (plugins.some(p=>p.installed && p.id===previous)) $('plugin').value=previous;
  $('plugin-cards').replaceChildren();
  for (const plugin of plugins) {
    const card=element('section',undefined,'card plugin-card');
    card.append(element('div',plugin.installed ? '● KURULU' : '○ KURULU DEĞİL',plugin.installed?'ping':'muted'),element('h2',plugin.name));
    card.append(element('p',`${plugin.id} · v${plugin.version}`,'small-note'));
    card.append(element('p',plugin.variant==='education' ? 'Analiz ve PDF dönüşümü; ek olarak iki sabit sentetik dosyada okuma ve yerel aktarım deneyi.' : 'Belge analizi ve PDF dönüşümü. Görev dışı erişim veya aktarım denemesi yapmaz.'));
    if(plugin.error) card.append(element('p',plugin.error,'error'));
    if(plugin.sha256) card.append(element('code','SHA-256: '+plugin.sha256,'package-hash'));
    const actions=element('div',undefined,'plugin-actions'); const link=element('a','Paketi indir'); link.href=plugin.download_url; link.className='text-link'; actions.append(link);
    const button=element('button',plugin.installed ? 'Eklentiyi kaldır' : 'Paketi kur','secondary'); button.disabled=pluginBusy;
    button.onclick=()=>pluginAction(async()=>{
      if(plugin.installed) await json('/api/plugins/uninstall',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({plugin_id:plugin.id})});
      else { const response=await fetch(plugin.download_url); if(!response.ok) throw Error('Paket indirilemedi.'); await installBlob(new File([await response.blob()],plugin.id+'.zip')); }
      return plugin.installed ? 'Eklenti kaldırıldı. Mevcut çalışma kopyası etkilenmez.' : 'Paket doğrulandı ve kuruldu. Belge dönüştür ekranından kullanabilirsiniz.';
    }); actions.append(button); card.append(actions); $('plugin-cards').append(card);
  }
  refreshButton();
}
async function installBlob(selected) {
  if(!selected || !selected.name.toLowerCase().endsWith('.zip') || selected.size>32768) throw Error('En fazla 32 KiB boyutunda bir laboratuvar ZIP paketi seçin.');
  await json('/api/plugins/install',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({package_base64:await base64File(selected)})});
}
async function pluginAction(action) {
  if(pluginBusy) return;
  pluginBusy=true; $('plugin-error').hidden=true; $('plugin-status').textContent=''; $('plugin-upload-button').disabled=true;
  for(const button of $('plugin-cards').querySelectorAll('button')) button.disabled=true;
  try { $('plugin-status').textContent=await action(); }
  catch(e) { $('plugin-error').textContent=e.message; $('plugin-error').hidden=false; }
  finally { pluginBusy=false; $('plugin-upload-button').disabled=false; await refreshPlugins().catch(e=>error(e.message)); }
}
$('plugin-upload-button').onclick=()=>$('plugin-file').click();
$('plugin-file').onchange=(event)=>{ const selected=event.target.files[0]; if(selected) pluginAction(async()=>{await installBlob(selected); return 'Seçilen paket doğrulandı ve kuruldu.';}); event.target.value=''; };
init();
