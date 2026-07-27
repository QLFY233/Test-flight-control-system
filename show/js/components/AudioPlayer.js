/**
 * AudioPlayer — TTS playback from base64 MP3 audio.
 * Handles autoplay policy by playing on user interaction.
 */

class AudioPlayer {
    /**
     * Play base64-encoded MP3 audio.
     * @param {string} base64 - base64 audio data (with or without data URI prefix)
     */
    static play(base64) {
        try {
            let src = base64;
            if (!base64.startsWith('data:')) {
                src = 'data:audio/mp3;base64,' + base64;
            }

            const audio = new Audio(src);

            // Attempt to play; if blocked by autoplay policy, add to queue
            const playPromise = audio.play();
            if (playPromise) {
                playPromise.catch((e) => {
                    if (e.name === 'NotAllowedError') {
                        console.warn('[AudioPlayer] autoplay blocked; will play on next user interaction');
                        AudioPlayer._queuePlay(audio);
                    } else {
                        console.error('[AudioPlayer] play error:', e);
                    }
                });
            }

            audio.addEventListener('ended', () => {
                audio.remove();
            });
        } catch (e) {
            console.error('[AudioPlayer] error creating audio:', e);
        }
    }

    /**
     * Queue an audio element to play on next user interaction.
     */
    static _queuePlay(audio) {
        const playQueued = () => {
            audio.play().catch(() => {});
            document.removeEventListener('click', playQueued);
            document.removeEventListener('touchstart', playQueued);
            document.removeEventListener('keydown', playQueued);
        };
        document.addEventListener('click', playQueued, { once: true });
        document.addEventListener('touchstart', playQueued, { once: true });
        document.addEventListener('keydown', playQueued, { once: true });
    }
}

export { AudioPlayer };
