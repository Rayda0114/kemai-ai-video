"""python check_music.py — real FFmpeg mixing, no external service calls."""
import os
from pathlib import Path
import tempfile
import numpy as np

with tempfile.TemporaryDirectory(prefix='kemai-music-check-') as tmp:
    os.environ['KEMAI_DATA_DIR'] = tmp
    from fastapi import HTTPException
    from server import clean_parameters
    from render import soundtrack, command, MUSIC
    valid = {'script': '這是一段合法長度的測試旁白。'}
    assert clean_parameters(dict(valid)).music == 'none'
    for values in ({'music':'../file'}, {'music_volume':'nan'}, {'music_volume':'inf'}, {'music_volume':'-.1'}, {'music_volume':'.41'}):
        try: clean_parameters({**valid, **values})
        except HTTPException as error: assert error.status_code == 422
        else: raise AssertionError(values)
    assert soundtrack({'music':'warm','music_volume':0}, 35) == soundtrack({},35)
    tone = Path(tmp)/'voice.wav'
    command(['ffmpeg','-y','-v','error','-f','lavfi','-i','sine=frequency=1000:duration=35',str(tone)])
    def mix(track, volume, silence=False):
        inputs, options = soundtrack({'music':track,'music_volume':volume},35)
        if silence:
            options[1] = options[1].replace('aresample=48000,asplit', 'aresample=48000,volume=0,asplit')
        raw = command(['ffmpeg','-v','error','-i',str(tone),'-i',str(tone),*inputs,*options,
                       '-t','35','-ac','1','-ar','16000','-f','f32le','pipe:1'])
        return np.frombuffer(raw,dtype='<f4')
    voice = mix('none',0)
    for track in MUSIC:
        mixed = mix(track,.4)
        assert abs(len(mixed)/16000-35)<.03 and np.all(np.isfinite(mixed))
        assert np.max(np.abs(mixed)) < .86
        residual = mixed[:len(voice)]-voice[:len(mixed)]
        # Detect the actual music after even the longest 30-second source loop.
        assert np.sqrt(np.mean(residual[31*16000:33*16000]**2))>.002
        lower = mix(track,.1)
        assert np.std(mixed-voice) > 2*np.std(lower-voice)
        if track == 'warm':
            bed = mix(track,.4,silence=True)
            assert np.std(residual[16000:-16000]) < .85*np.std(bed[16000:-16000])
        print(track, '35 seconds, loops, volume change and peak limit passed')
print('Passed: music input bounds, no-music/zero-volume compatibility and all real soundtrack filters.')
