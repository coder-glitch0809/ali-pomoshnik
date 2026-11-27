"""Import scene narration exported from Google AI Studio, without a speech API."""
import io
import wave
from .config import config

MAX_BYTES = 20 * 1024 * 1024


def validate(data):
    if not data or len(data) > MAX_BYTES:
        raise ValueError('WAV fayli bo‘sh yoki 20 MB dan katta')
    try:
        with wave.open(io.BytesIO(data), 'rb') as audio:
            duration = audio.getnframes() / audio.getframerate()
            if not 0.2 <= duration <= 90 or audio.getnchannels() not in (1, 2):
                raise ValueError('Har sahna uchun 0,2–90 soniyali mono yoki stereo WAV kerak')
            if audio.getsampwidth() not in (1, 2, 3, 4):
                raise ValueError('WAV bit chuqurligi qo‘llanmaydi')
            expected = audio.getnframes() * audio.getnchannels() * audio.getsampwidth()
            if len(audio.readframes(audio.getnframes())) != expected:
                raise ValueError('WAV fayli to‘liq yuklanmagan')
            return round(duration, 3)
    except (wave.Error, EOFError, ZeroDivisionError) as error:
        raise ValueError('AI Studio’dan yuklangan haqiqiy PCM WAV faylini tanlang') from error


def path(job_id, index):
    from . import creative_video as studio
    job = studio.get(job_id)
    if not job or not 1 <= index <= len((job.get('story') or {}).get('scenes', [])):
        return None
    target = config.data_dir / 'creative_videos' / job_id / f'narration-{index}.wav'
    return target if target.is_file() and not target.is_symlink() else None


def save(job_id, index, data):
    from . import creative_video as studio
    job = studio.get(job_id)
    scenes = (job or {}).get('story', {}).get('scenes', [])
    if not job or job.get('status') != 'ready' or not 1 <= index <= len(scenes):
        raise ValueError('Avval sahnalar tayyor bo‘lishi kerak')
    duration = validate(data)
    folder = config.data_dir / 'creative_videos' / job_id
    with studio._lock:
        if studio._jobs[job_id].get('status') != 'ready':
            raise ValueError('Video yig‘ilmoqda; ovozni hozir o‘zgartirib bo‘lmaydi')
        folder.mkdir(parents=True, exist_ok=True)
        temp = folder / f'narration-{index}.tmp'
        temp.write_bytes(data)
        temp.replace(folder / f'narration-{index}.wav')
        studio._jobs[job_id].setdefault('scene_audio', {})[str(index)] = {
            'url': f'/api/creative-video/{job_id}/audio/{index}', 'duration': duration}
        speaker = str(scenes[index-1].get('speaker') or 'Hikoyachi')
        studio._jobs[job_id].setdefault('voices', {})[speaker] = 'aistudio'
    studio._update(job_id)
    return studio.get(job_id)


def use_aistudio(job_id):
    from . import creative_video as studio
    job = studio.get(job_id)
    scenes = (job or {}).get('story', {}).get('scenes', [])
    if not scenes or job.get('status') not in ('ready', 'error', 'done'):
        raise ValueError('Avval sahnalar tayyor bo‘lishi kerak')
    if any(studio.scene_path(job_id, i+1) is None for i in range(len(scenes))):
        raise ValueError('Barcha sahna rasmlari hali tayyor emas')
    with studio._lock:
        if studio._jobs[job_id].get('status') not in ('ready', 'error', 'done'):
            raise ValueError('Video yig‘ilmoqda; ovoz rejimini hozir o‘zgartirib bo‘lmaydi')
        studio._jobs[job_id].update(status='ready', review=True, progress=60,
            voices={str(s.get('speaker') or 'Hikoyachi'): 'aistudio' for s in scenes},
            message='AI Studio rejimi: har sahna matnidan ovoz yarating va WAV faylini biriktiring.')
    studio._update(job_id)
    return studio.get(job_id)
