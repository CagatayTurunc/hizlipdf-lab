const $ = (id) => document.getElementById(id);
let file = null, health = null, currentRun = null, busy = false, plugins = [], pluginBusy = false;
let benchmarkRunning = false;
const syscallLabels = { allowed: 'BAŞARILI', error: 'HATA', pending: 'BAĞLANTI BEKLEMEDE' };
const names = {PROCESS_STARTED:'İşçi başladı',CONVERSION_STARTED:'Dönüşüm başladı',CONVERSION_FINISHED:'Dönüşüm tamamlandı',LAB_PING:'Yerel bağlantı testi',LAB_PROBE_FINISHED:'Ek deney adımı tamamlandı',TASK_READ_ATTEMPT:'Görev dışı okuma denemesi',TASK_READ:'Görev dışı okuma',CONTENT:'İçerik aktarım denemesi',EXTRA_ACTIONS:'Ek davranışlar'};
const results = {ok:'Başarılı (işçi)',running:'Denendi',failed:'Başarısız / hata kaydı',acknowledged:'Alıcı onayı bildirildi',not_attempted:'Denenmedi',rejected_content:'Sentetik içerik doğrulaması reddetti'};

Object.assign(names,{PLUGIN_LOADED:'Kurulu paket yüklendi',PLUGIN_FAILED:'Paket yüklenemedi',ANALYSIS_FINISHED:'Belge analiz edildi'});
function view(name) {
  for (const key of ['user','plugins','observer','benchmark']) {
    const el = $(key+'-view'), tab = $(key+'-tab');
    if (el) el.hidden = key !== name;
    if (tab) tab.classList.toggle('active', key === name);
  }
}
$('user-tab').onclick = () => view('user');
$('plugins-tab').onclick = $('manage-plugins').onclick = () => view('plugins');
$('observer-tab').onclick = $('reveal-button').onclick = () => view('observer');
$('benchmark-tab').onclick = () => view('benchmark');
function error(message) { $('error').textContent = message; $('error').hidden = !message; }
function refreshButton() { $('convert-button').disabled = busy || benchmarkRunning || !file || !health?.converter || !$('plugin').value; }
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
  if (busy || benchmarkRunning || !file) return;
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
  if ($('forensic-report-btn')) $('forensic-report-btn').href = `/api/runs/${data.run_id}/report`;
  $('run-verdict').textContent = data.verdict
    ? `${data.verdict.label} · ${data.verdict.summary}`
    : 'Doğrulanmadı · Deney kaydı henüz tamamlanmadı.';
  $('metric-pdf').textContent = data.pdf && data.status === 'completed' ? 'Hazır' : data.status === 'failed' ? 'Hata' : 'İşleniyor';
  $('metric-reads').textContent = data.metrics?.read_sources_worker_reported ?? '—';
  $('metric-sources').textContent = data.receiver.filter(e=>e.kind==='CONTENT').length;
  $('metric-bytes').textContent = `${data.receiver.reduce((s,e)=>s+e.accepted_bytes,0)} B`;
  $('selected-file').textContent = '✓ Seçilen belge: ' + data.filename;
  $('access-list').replaceChildren();
  const reads = data.events.filter(e=>e.event==='TASK_READ');
  if (!reads.length) $('access-list').append(element('p',data.plugin==='normal' ? 'Normal eklenti: ek erişim denenmez.' : 'Okuma sonucu henüz yok.','empty-record'));
  for (const entry of reads) { const row = element('div',undefined,'access-row'); row.append(element('strong',entry.source)); row.append(element('span', entry.result==='ok' ? 'GÖREV DIŞI · Okundu (işçi bildirimi)' : `GÖREV DIŞI · ${entry.error || entry.result}`)); $('access-list').append(row); }
  $('receiver-list').replaceChildren();
  if (data.receiver.some(e=>e.kind==='LAB_PING')) $('receiver-list').append(element('div','● LAB-PING yerel alıcı tarafından kabul edildi','ping'));
  const contents = data.receiver.filter(e=>e.kind==='CONTENT');
  if (!contents.length) $('receiver-list').append(element('p','Görev dışı içerik kabul kaydı yok. Bu durum tek başına ağın engellendiğini kanıtlamaz.','empty-record'));
  for (const entry of contents) { const card = element('div',undefined,'receiver-record'); card.append(element('strong',entry.source)); card.append(element('pre',entry.content)); card.append(element('small',`${entry.accepted_bytes} bayt · Alıcı tarafından kabul edildi`)); $('receiver-list').append(card); }
  const inspector = $('packet-inspector');
  inspector.replaceChildren();
  inspector.append(element('p', data.network_audit?.summary || 'Bağlantı sonucu doğrulanmadı.', 'small-note'));
  const requests = data.receiver.filter(entry => entry.http_record);
  if (requests.length) {
    inspector.append(element('p', 'Görünüm kabul edilen istekten yeniden oluşturulur. Çalışma anahtarı çıkarılır. Hex dökümü bu görünümün ilk 512 baytını gösterir.', 'small-note'));
  }
  for (const request of requests) {
    const card = element('section', undefined, 'packet-card');
    const header = element('div', undefined, 'packet-header');
    const tabs = element('div', undefined, 'packet-tabs');
    const textButton = element('button', 'HTTP görünümü', 'packet-tab-btn active');
    const hexButton = element('button', 'Hex dökümü', 'packet-tab-btn');
    const http = element('pre', request.http_record, 'packet-body-pre');
    const hex = element('pre', request.http_record_hex, 'packet-body-pre hexdump-pre');
    function showHex(show) {
      http.hidden = show;
      hex.hidden = !show;
      textButton.classList.toggle('active', !show);
      hexButton.classList.toggle('active', show);
      textButton.setAttribute('aria-pressed', String(!show));
      hexButton.setAttribute('aria-pressed', String(show));
    }
    showHex(false);
    textButton.onclick = () => showHex(false);
    hexButton.onclick = () => showHex(true);
    tabs.append(textButton, hexButton);
    header.append(element('span', 'POST', 'packet-method-badge allowed'),
      element('span', `/collect · ${request.source || request.kind}`, 'packet-uri'), tabs);
    card.append(header, http, hex);
    inspector.append(card);
  }
  const mitreGrid = $('mitre-grid');
  if (mitreGrid) {
    mitreGrid.replaceChildren();
    const mitreList = data.mitre_matrix || [];
    if (!mitreList.length) {
      mitreGrid.append(element('p', 'MITRE ATT&CK eşleme kaydı bulunamadı.', 'empty-record'));
    } else {
      for (const item of mitreList) {
        const itemCard = element('div', undefined, `mitre-card-item status-${item.status}`);
        const header = element('div', undefined, 'mitre-item-header');
        const codePill = element('span', item.technique_id, 'mitre-id-pill');
        const statusBadge = element('span', item.status_label, `mitre-status-badge ${item.status}`);
        header.append(codePill, statusBadge);
        const title = element('h3', item.name, 'mitre-technique-title');
        const tactic = element('div', item.tactic, 'mitre-tactic-label');
        const desc = element('p', item.detail, 'mitre-detail-text');
        itemCard.append(header, title, tactic, desc);
        if (item.mitigation) {
          itemCard.append(element('div', `Savunma: ${item.mitigation}`, 'mitre-mitigation-tag'));
        }
        mitreGrid.append(itemCard);
      }
    }
  }
  const term = $('syscall-terminal');
  if (term) {
    term.replaceChildren();
    const syscalls = data.syscalls || [];
    if (!syscalls.length) {
      term.append(element('p', 'İlgili sistem çağrısı kaydı bulunamadı.', 'empty-record'));
    } else {
      for (const call of syscalls) {
        const line = element('div', undefined, 'syscall-line');
        const badge = element('span', syscallLabels[call.status] || 'SONUÇ BELİRSİZ', `syscall-badge ${call.status}`);
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
  $('evidence-note').textContent = data.file_audit?.summary || 'Dosya açma sonucu doğrulanmadı.';
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
const benchmarkRepeats = 5;

async function benchmarkTrial(profile, documentData) {
  const { run_id: runId } = await json('/api/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...documentData, profile, plugin_id: 'hizlipdf.education' })
  });
  const deadline = Date.now() + 95000;
  try {
    while (Date.now() < deadline) {
      const data = await json(`/api/runs/${runId}`, { signal: AbortSignal.timeout(5000) });
      if (data.status === 'completed' || data.status === 'failed') return data;
      await new Promise(resolve => setTimeout(resolve, 350));
    }
    return { run_id: runId, status: 'unknown', error: 'Çalışma zamanında doğrulanamadı.' };
  } catch (err) {
    return { run_id: runId, status: 'unknown', error: err.message };
  }
}

async function runBenchmark() {
  if (benchmarkRunning || busy) return;
  benchmarkRunning = true;
  refreshButton();
  $('run-benchmark-btn').disabled = true;
  $('benchmark-progress').hidden = false;
  $('benchmark-results').hidden = true;

  function progress(done, count, status) {
    const percent = Math.round(done * 100 / count);
    $('benchmark-pct').textContent = `%${percent}`;
    $('benchmark-bar-fill').style.width = `${percent}%`;
    $('benchmark-status-text').textContent = status;
  }

  try {
    progress(0, 1, 'Deney koşulları kontrol ediliyor…');
    health = await json('/api/health');
    if (!health.converter || !health.profiles.every(profile => profile.available)) {
      throw Error('Dört profilin karşılaştırılması için LibreOffice ve çalışan Linux bubblewrap ortamı gerekli.');
    }
    const installed = (await json('/api/plugins')).plugins;
    if (!installed.some(plugin => plugin.id === 'hizlipdf.education' && plugin.installed)) {
      throw Error('Önce eğitim eklentisini kurun.');
    }

    let sample = file;
    if (!sample) {
      const response = await fetch('/api/sample');
      if (!response.ok) throw Error('Örnek belge alınamadı.');
      sample = new File([await response.blob()], 'Musteri_Teklifi.docx');
    }
    const documentData = { filename: sample.name, content_base64: await base64File(sample) };
    const profiles = health.profiles;
    const trials = Object.fromEntries(profiles.map(profile => [profile.id, []]));
    const total = profiles.length * (benchmarkRepeats + 1);
    let done = 0;

    // Round 0 warms each profile. Rotate the starting profile on each measured round.
    for (let round = 0; round <= benchmarkRepeats; round++) {
      for (let offset = 0; offset < profiles.length; offset++) {
        const profile = profiles[(round + offset) % profiles.length];
        const phase = round === 0 ? 'Isınma' : `Tur ${round}/${benchmarkRepeats}`;
        progress(done, total, `${phase} · Profil ${profile.id}`);
        let data;
        try {
          data = await benchmarkTrial(profile.id, documentData);
        } catch (err) {
          data = { status: 'unknown', error: err.message };
        }
        trials[profile.id].push({ round, data });
        done++;
      }
    }
    progress(done, total, 'Deney serisi tamamlandı.');
    renderBenchmarkResults(profiles, trials);
  } catch (err) {
    $('benchmark-status-text').textContent = err.message;
  } finally {
    benchmarkRunning = false;
    $('run-benchmark-btn').disabled = false;
    refreshButton();
  }
}

function measurement(values) {
  const sorted = values.filter(value => Number.isFinite(value) && value >= 0).sort((a, b) => a - b);
  if (!sorted.length) return null;
  const middle = Math.floor(sorted.length / 2);
  const median = sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
  return { median, min: sorted[0], max: sorted.at(-1), count: sorted.length };
}
function measurementText(stats, unit) {
  if (!stats) return 'Doğrulanmadı';
  return `${stats.median} ${unit} · ${stats.min}–${stats.max} ${unit} · n=${stats.count}`;
}
function renderBenchmarkResults(profiles, trials) {
  const cards = $('benchmark-cols');
  cards.replaceChildren();
  const summary = {};
  for (const profile of profiles) {
    const attempts = trials[profile.id];
    const completed = attempts.filter(({round, data}) =>
      round > 0 && data.status === 'completed' && data.pdf?.structurally_valid
    ).map(({data}) => data);
    const durations = completed.map(data => data.total_ms);
    const bytes = completed.filter(data => data.receiver.length
      || (data.receiver_health?.before && data.receiver_health?.after)
    ).map(data => data.metrics?.accepted_bytes);
    const total = measurement(durations);
    const accepted = measurement(bytes);
    const conversion = measurement(completed.map(data =>
      data.events.find(event => event.event === 'CONVERSION_FINISHED' && event.result === 'ok')?.duration_ms
    ));
    const extra = measurement(completed.map(data =>
      data.events.find(event => event.event === 'LAB_PROBE_FINISHED')?.duration_ms
    ));
    summary[profile.id] = { total, accepted };

    const opened = completed.filter(data => data.file_audit?.status === 'opened').length;
    const unavailableFiles = completed.filter(data => data.file_audit?.status === 'unavailable').length;
    const reachable = completed.filter(data => data.network_audit?.status === 'reachable').length;
    const unreachable = completed.filter(data => data.network_audit?.status === 'unreachable').length;
    const card = element('section', undefined, 'benchmark-col-card');
    card.append(element('span', `Profil ${profile.id}`, 'benchmark-col-badge'),
      element('h3', profile.name, 'benchmark-col-title'));
    const metrics = [
      ['Geçerli PDF', `${completed.length}/${benchmarkRepeats}`],
      ['Alıcının kabul ettiği içerik', measurementText(accepted, 'bayt')],
      ['İki dosya için açma sonucu', `${opened} başarılı · ${unavailableFiles} başarısız · ${completed.length - opened - unavailableFiles} doğrulanmadı`],
      ['Yerel alıcıya bağlantı', `${reachable} erişildi · ${unreachable} başarısız · ${completed.length - reachable - unreachable} doğrulanmadı`],
      ['Toplam süre', measurementText(total, 'ms')],
      ['PDF dönüşümü (işçi)', measurementText(conversion, 'ms')],
      ['Ek deney adımı (işçi)', measurementText(extra, 'ms')]
    ];
    for (const [label, value] of metrics) {
      const row = element('div', undefined, 'benchmark-metric-item');
      row.append(element('span', label, 'benchmark-metric-label'), element('strong', value, 'benchmark-metric-value'));
      card.append(row);
    }
    const details = element('details');
    details.append(element('summary', 'Çalışma kayıtları'));
    const list = element('ul');
    for (const {round, data} of attempts) {
      const label = round ? `Tur ${round}` : 'Isınma';
      const item = element('li');
      const status = data.verdict?.label || 'Doğrulanmadı';
      if (data.run_id) {
        const link = element('a', label, 'text-link');
        link.href = `/api/runs/${data.run_id}/report`;
        link.target = '_blank';
        link.rel = 'noopener';
        item.append(link, ` · ${status}`);
      } else {
        item.textContent = `${label} · ${status}`;
      }
      if (data.error) item.append(` · ${data.error}`);
      list.append(item);
    }
    details.append(list);
    card.append(details);
    cards.append(card);
  }

  renderBenchmarkChart($('chart-data-leak'), profiles, summary, 'accepted', 'B');
  renderBenchmarkChart($('chart-latency'), profiles, summary, 'total', 'ms');
  const a = summary.A.total, d = summary.D.total;
  $('overhead-summary-text').textContent = a?.count === benchmarkRepeats && d?.count === benchmarkRepeats
    ? `D ile A arasındaki toplam süre medyanı farkı ${d.median - a.median} ms. Toplam süre, dosya hazırlığı, dönüşüm, ek deney adımı ve çıktı kontrolünü kapsar.`
    : `A ile D arasındaki medyan farkı için iki profilde de ${benchmarkRepeats} geçerli ölçüm gerekiyor.`;
  $('benchmark-results').hidden = false;
}

function renderBenchmarkChart(container, profiles, summary, key, unit) {
  container.replaceChildren();
  const max = Math.max(1, ...profiles.map(profile => summary[profile.id][key]?.median ?? 0));
  for (const profile of profiles) {
    const stats = summary[profile.id][key];
    const row = element('div', undefined, 'chart-row');
    row.append(element('div', `Profil ${profile.id}`, 'chart-row-label'));
    const track = element('div', undefined, 'chart-row-track');
    if (stats) {
      const fill = element('div', undefined, 'chart-row-fill fill-latency');
      fill.style.width = `${stats.median * 100 / max}%`;
      track.append(fill);
    }
    row.append(track, element('div', stats ? `${stats.median} ${unit}` : 'Doğrulanmadı', 'chart-row-value'));
    container.append(row);
  }
}
$('run-benchmark-btn').onclick = runBenchmark;
init();
