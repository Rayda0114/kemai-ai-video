"""Build our three instrumental loops from oscillators, with no sampled recordings.
Run manually with the existing video environment: python make_music.py.
"""
from pathlib import Path
import subprocess
import tempfile
import wave
import numpy as np
from imageio_ffmpeg import get_ffmpeg_exe

RATE = 44100
# Eight bars each; original arrangements, MIDI pitches, no external audio assets.
TRACKS = {
    'warm': (80, [[48,55,59,64],[45,52,55,60],[41,48,52,57],[43,50,55,62]]),
    'bright': (108, [[50,57,62,66],[47,54,59,62],[43,50,57,62],[45,52,57,61]]),
    'calm': (64, [[45,52,59,60],[41,48,55,60],[48,55,59,64],[43,50,57,62]]),
}


def compose(name, bpm, chords):
    beat = 60 / bpm
    length = round(32 * beat * RATE)
    # Three passes let reverb/note tails wrap naturally into the middle loop.
    audio = np.zeros((length * 3, 2), dtype=np.float32)
    rng = np.random.default_rng(74)

    def add(samples, start, gain, pan=0):
        offset = round(start * RATE)
        count = min(len(samples), len(audio) - offset)
        if count > 0:
            audio[offset:offset+count, 0] += samples[:count] * gain * np.sqrt((1-pan)/2)
            audio[offset:offset+count, 1] += samples[:count] * gain * np.sqrt((1+pan)/2)

    def note(pitch, start, duration, gain, pad=False, pan=0):
        t = np.arange(round(duration * RATE)) / RATE
        f = 440 * 2 ** ((pitch - 69) / 12)
        sound = (np.sin(2*np.pi*f*t) + .24*np.sin(2*np.pi*f*2*t)*np.exp(-t*2)
                 + .08*np.sin(2*np.pi*f*3*t)*np.exp(-t*4))
        envelope = (1-np.exp(-t/(.22 if pad else .008))) * np.exp(-t/(2.8 if pad else .65))
        envelope *= np.minimum(1, (duration-t)/.15)
        sound *= envelope
        add(sound, start, gain, pan)
        for delay, level in ((.19,.13),(.37,.07)):
            add(sound, start+delay, gain*level, -pan)

    for bar in range(24):
        chord = chords[(bar//2) % 4]
        start = bar * 4 * beat
        note(chord[0]-12, start, 3.8*beat, .18, pad=True)
        for j, pitch in enumerate(chord[1:]):
            note(pitch, start+j*.015, 4.8*beat, .11, pad=True, pan=(j-1)*.3)
        steps = 4 if name == 'calm' else 8
        for step in range(steps):
            pitch = chord[1 + [0,1,2,1,2,0,1,2][step] % 3] + 12
            note(pitch, start+step*4*beat/steps, 2.5*beat,
                 .10 if name == 'calm' else .16, pan=.3*(-1)**step)
        if name == 'bright':
            for step in range(4):
                t = np.arange(round(.22*RATE))/RATE
                kick = np.sin(2*np.pi*(48*t + 35*.025*(1-np.exp(-t/.025)))) * np.exp(-t*20)
                add(kick, start+step*beat, .24)
                noise = rng.normal(0, 1, len(t))
                hat = np.diff(noise, prepend=noise[0]) * np.exp(-t*75)
                add(hat, start+(step+.5)*beat, .013, .15)
    return audio[length:2*length]


if __name__ == '__main__':
    output = Path(__file__).resolve().parent/'static/music'
    output.mkdir(exist_ok=True)
    for name, (bpm, chords) in TRACKS.items():
        samples = compose(name, bpm, chords)
        samples *= .72 / max(.001, np.max(np.abs(samples)))
        with tempfile.TemporaryDirectory(prefix='kemai-music-') as tmp:
            path = Path(tmp)/'loop.wav'
            with wave.open(str(path), 'wb') as wav:
                wav.setparams((2, 2, RATE, 0, 'NONE', 'not compressed'))
                wav.writeframes((samples*32767).astype('<i2').tobytes())
            subprocess.run([get_ffmpeg_exe(), '-y', '-v', 'error', '-i', str(path),
                            '-af', 'loudnorm=I=-18:TP=-2:LRA=7', '-ar', str(RATE),
                            '-c:a', 'libmp3lame', '-b:a', '128k', str(output/f'{name}.mp3')], check=True)
        print(name, round(len(samples)/RATE, 2), (output/f'{name}.mp3').stat().st_size)
