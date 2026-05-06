;Configured at runtime memory and history in amount of characters:
(= (maxFeedback) (empty))
(= (maxRecallItems) (empty))
(= (maxEpisodeRecallLines) (empty))
(= (maxHistory) (empty))
(= (embeddingprovider) (empty))

(= (initMemory)
   (progn (println! "Initializing memory")
          (configure maxFeedback 50000)
          (configure maxRecallItems 20)
          (configure maxEpisodeRecallLines 20)
          (configure maxHistory 30000)
          (configure embeddingprovider OpenAI) ;OpenAI or Local
          (if (== (embeddingprovider) Local)
              (py-call (lib_llm_ext.initLocalEmbedding)) _)))

(= (getPrompt)
   (read-file (library mettaclaw ./memory/prompt.txt)))

(= (getHistory)
   (let $ret (read-file (library mettaclaw ./memory/history.metta))
        (last_chars $ret (maxHistory))))

(= (addToHistory $lastmessage $response $sexpr $msgnew)
   (if $msgnew
       (if (== (get-state &error) ())
           (appendToHistory ((get_time_as_string) (newline) "HUMAN_MESSAGE: " $lastmessage (newline) $response (newline)))
           (appendToHistory ((get_time_as_string) (newline) "HUMAN_MESSAGE: " $lastmessage (newline) $response (newline) ERROR_FEEDBACK: (get-state &error))))
       (if (== (get-state &error) ())
           (appendToHistory ((get_time_as_string) (newline) $response (newline)))
           (appendToHistory ((get_time_as_string) (newline) $response (newline) ERROR_FEEDBACK: (get-state &error))))))

(= (embed $str)
   (if (== (embeddingprovider) Local)
       (py-call (lib_llm_ext.useLocalEmbedding (string-safe $str)))
       (useGPTEmbedding (string-safe $str))))

(= (appendToHistory $addition)
   (append-file (library mettaclaw ./memory/history.metta) (swrite $addition)))

(= (remember $str)
   (progn (py-call (lib_chromadb.remember $str (embed $str) (get_time_as_string)))
          REMEMBER-SUCCESS))

(= (query $str)
   (let $candidates (collapse (let* (($queryresults (py-call (lib_chromadb.query_with_ids_and_dists (embed $str) (* (promotionInflationFactor) (maxRecallItems)))))
                                     ($current_time (get_time))
                                     (($uuid $time $message $distance) (superpose $queryresults))
                                     ($promotion (py-call (helper.promotion_get_value $uuid 0.0)))
                                     ($lasttime (py-call (helper.promotion_get_lasttime $uuid 0.0)))
                                     ($t (- $current_time $lasttime))
                                     ($current_promotion (* $promotion (pow-math (+ 1.0 (/ $t 86400.0)) (- 0.0 0.7)))))
                                    ((- 0.0 $current_promotion) $distance $uuid $time $message)))
         (let $best (takeK (maxRecallItems) (msort $candidates))
              (collapse (let ($_ $_ $uuid $time $message) (superpose $best)
                             ($uuid $time $message))))))

(= (episodes $time)
   (py-call (helper.around_time $time (maxEpisodeRecallLines))))

(= (promote $uuid)
   (let $v (py-call (helper.promotion_get_value $uuid 0))
        (progn (py-call (helper.promotion_set_value $uuid (+ 1.0 $v)))
               (py-call (helper.promotion_set_lasttime $uuid (get_time)))
               (py-call (helper.promotion_commit)))))
