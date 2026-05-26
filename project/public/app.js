document.addEventListener('DOMContentLoaded', loadVideos);

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function showProgressPanel(show) {
    const panel = document.getElementById('progressPanel');
    panel.classList.toggle('hidden', !show);
    panel.setAttribute('aria-hidden', show ? 'false' : 'true');
}

function updateProgress(progress) {
    const panel = document.getElementById('progressPanel');
    const bar = document.getElementById('progressBar');
    const info = document.getElementById('progressInfo');
    const percentEl = document.getElementById('progressPercent');
    const meta = document.getElementById('progressMeta');

    const percent = Math.min(100, Math.max(0, Number(progress.percent) || 0));
    const status = progress.status || 'downloading';
    const isWaiting = ['pending', 'starting', 'preparing'].includes(status);
    const hasProgress = percent > 0;

    if (hasProgress) {
        bar.style.width = `${percent}%`;
        panel.classList.remove('indeterminate');
    } else {
        bar.style.width = '35%';
        panel.classList.add('indeterminate');
    }

    info.classList.remove('hidden');

    if (isWaiting && !hasProgress) {
        percentEl.textContent = '...';
    } else {
        percentEl.textContent = `${Math.round(percent)}%`;
    }

    const parts = [];
    if (isWaiting && !hasProgress) parts.push('Подготовка');
    if (progress.total) parts.push(progress.total);
    if (progress.speed) parts.push(progress.speed);
    if (progress.eta) parts.push(`ETA ${progress.eta}`);
    meta.textContent = parts.join(' · ');
}

async function pollJob(jobId) {
    while (true) {
        const response = await fetch(`/download/${jobId}`);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                typeof data.detail === 'string' ? data.detail : 'Ошибка загрузки'
            );
        }

        updateProgress(data.progress || {});

        if (data.status === 'completed') {
            return data;
        }
        if (data.status === 'failed') {
            throw new Error(data.error || 'Не удалось скачать видео');
        }

        await sleep(250);
    }
}

async function startDownload() {
    const urlInput = document.getElementById('urlInput');
    const statusDiv = document.getElementById('status');
    const downloadBtn = document.getElementById('downloadBtn');
    const qualitySelect = document.getElementById('qualitySelect');

    const url = urlInput.value.trim();
    const quality = qualitySelect.value;

    if (!url) {
        alert('Пожалуйста, вставьте ссылку!');
        return;
    }

    downloadBtn.disabled = true;
    qualitySelect.disabled = true;
    statusDiv.textContent = '';
    statusDiv.style.color = '#007bff';
    showProgressPanel(true);
    updateProgress({ percent: 0, status: 'starting' });

    try {
        const startResponse = await fetch('/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, quality }),
        });

        const startData = await startResponse.json();

        if (!startResponse.ok) {
            const message =
                typeof startData.detail === 'string'
                    ? startData.detail
                    : 'Не удалось начать загрузку';
            throw new Error(message);
        }

        const result = await pollJob(startData.job_id);

        statusDiv.style.color = '#28a745';
        statusDiv.textContent = 'Видео успешно скачано!';
        urlInput.value = '';
        loadVideos();
    } catch (error) {
        statusDiv.style.color = '#dc3545';
        statusDiv.textContent = `Ошибка: ${error.message}`;
    } finally {
        downloadBtn.disabled = false;
        qualitySelect.disabled = false;
        setTimeout(() => showProgressPanel(false), 1500);
    }
}

async function loadVideos() {
    const tableBody = document.getElementById('videoTableBody');
    tableBody.innerHTML = '<tr><td colspan="4">Загрузка истории...</td></tr>';

    try {
        const response = await fetch('/videos');
        const data = await response.json();

        if (data.success) {
            tableBody.innerHTML = '';

            if (data.videos.length === 0) {
                tableBody.innerHTML = '<tr><td colspan="4">История пуста</td></tr>';
                return;
            }

            data.videos.forEach((video) => {
                const tr = document.createElement('tr');
                const qualityLabel = formatQualityLabel(video.quality);
                const qualityTag = qualityLabel
                    ? `<small style="color:#28a745;">${qualityLabel}</small><br>`
                    : '';
                tr.innerHTML = `
                    <td>${escapeHtml(video.title)} <br>
                        ${qualityTag}
                        <small style="color:gray;">${escapeHtml(video.filename)}</small></td>
                    <td>${escapeHtml(video.filesize || 'Неизвестно')}</td>
                    <td>${escapeHtml(video.duration || '00:00')}</td>
                    <td><button class="delete-btn" onclick="deleteVideo(${video.id})">Удалить</button></td>
                `;
                tableBody.appendChild(tr);
            });
        }
    } catch {
        tableBody.innerHTML =
            '<tr><td colspan="4">Не удалось загрузить историю</td></tr>';
    }
}

function formatQualityLabel(quality) {
    const labels = {
        small: 'Малый размер',
        best: 'Лучшее',
        '360': '360p',
        '480': '480p',
        '720': '720p',
        '1080': '1080p',
    };
    return labels[quality] || quality || '';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text ?? '';
    return div.innerHTML;
}

async function deleteVideo(id) {
    if (!confirm('Точно удалить это видео?')) return;

    try {
        const response = await fetch(`/videos/${id}`, { method: 'DELETE' });
        const data = await response.json();

        if (data.success) {
            loadVideos();
        } else {
            alert('Ошибка при удалении');
        }
    } catch {
        alert('Ошибка сети при удалении');
    }
}
