!(import! &self (library mettaclaw ./src/music_generation.py))

(= (music-generate $spec)
   (py-call (music_generation.generate $spec)))

(= (music-list $spec)
   (py-call (music_generation.list_outputs $spec)))

(= (music-inspect $spec)
   (py-call (music_generation.inspect $spec)))

(= (music-gttm-energy $spec)
   (py-call (music_generation.gttm_energy $spec)))

(= (music-plan-method-a $spec)
   (py-call (music_generation.plan_method_a $spec)))

(= (music-decode-score $spec)
   (py-call (music_generation.decode_score $spec)))

(= (music-render-midi $spec)
   (py-call (music_generation.render_midi_partition $spec)))

(= (music-summarize-midi $spec)
   (py-call (music_generation.summarize_midi_partition $spec)))
