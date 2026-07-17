(= (getSkills)
   (;INTERNAL:
    "- Remember a particular string such as skills and memories: remember string"
    "- Query long-term embedding memory for skills and memories with short phrases only: query string"
    "- Episodes searches history for episodes around a time stamp, time format is same as in TIME: episodes %Y-%m-%d %H:%M:%S"
    "- Pin a certain string as short-term working memory item to keep track of task state: pin string"
    "- Promote a memory that you found useful, to make it easier to be recalled in the future in similar context: promote time_string"
    "- Demote a memory that you do not find useful or not anymore, to remove its promotion advantage: demote time_string"
    ;SHELL AND FILE I/O:
    "- Execute shell command without apostrophe in string, it returns the command output to you: shell string"
    "- Read file to string: read-file filename"
    "- Write string to file: write-file filename string"
    "- Append line to file: append-file filename string",
    ;COMMUNICATION CHANNELS:
    "- Send message to user: send string"
    "- Search the web: search string"
    ;MUSIC GENERATION:
    "- Generate symbolic multi-track MIDI by calling the sibling musicGeneration project. Use compact specs like beats=8 seed=42 edo=12 tempo=120 meter=4/4 groove=straight out=music_outputs: music-generate string"
    "- List recent generated music artifacts, optionally with out=music_outputs: music-list string"
    "- Inspect a generated music manifest path, or inspect latest with out=music_outputs: music-inspect string"
    "- Compute GTTM transition energy between two BeatStates. Optional prev=8 comma-separated ints next=8 comma-separated ints time=0 edo=12: music-gttm-energy string"
    "- Run only Method A planning and save a BeatState path JSON. Use beats=8 seed=42 edo=12 out=music_outputs: music-plan-method-a string"
    "- Decode latest or specified path JSON into score JSON. Use path=... or out=music_outputs: music-decode-score string"
    "- Render latest or specified score JSON to MIDI. Use score=... edo=12 or out=music_outputs edo=19: music-render-midi string"
    "- Summarize latest or specified MIDI artifact. Use midi=... or out=music_outputs: music-summarize-midi string"
    ;CODE EXECUTION:
    "- Execute MeTTa expression: metta sexpression"
    "- Example to invoke Non-Axiomatic Logic via MeTTa: "
    " metta (|- ((--> (× sam garfield) friend) (stv 1.0 0.9))"
    "           ((--> garfield animal) (stv 1.0 0.9)))"
    " metta (|- ((==> (--> (× $1 elephant) eat) (--> $1 ([] dangerous))) (stv 1.0 0.9))"
    "           ((--> (× tiger elephant) eat) (stv 1.0 0.9)))"
    "- Also: note the $1 for independent variables, and for negated knowledge use (stv 0.0 0.9)"
    "- Additionally |- also works for revision, to merge evidence even when the term of both premises is the same."
    "- Also, you can use |-t for temporal inference (sequence formation &/, induction of =/>, deduction, syllogistic inference on =/> etc.)"
    "- You can use: metta (add-atom &persistent sexpression) to add expressions to the persistent atomspace up to a configured maximum size."
    "- Functions added there are also persisted and can be called directly via the metta command, and check for current content with: metta (get-atoms &persistent)"))

(= (read-file $file)
   (progn (translatePredicate (exists_file $file))
          (translatePredicate (read_file_to_string $file $content ()))
          $content))

(= (write-file $file $str)
   (progn (translatePredicate (open $file write $Out))
          (translatePredicate (write $Out $str))
          (translatePredicate (close $Out))
          WRITE-FILE-SUCCESS))

(= (append-file $file $str)
   (progn (translatePredicate (exists_file $file))
          (translatePredicate (open $file append $Out))
          (translatePredicate (write $Out $str))
          (translatePredicate (nl $Out)),
          (translatePredicate (close $Out))
          APPEND-FILE-SUCCESS))

!(import_prolog_functions_from_file (library mettaclaw ./src/skills.pl) (shell first_char gc))

!(import_prolog_function call_with_inference_limit)
(= (metta $str)
   (let $code (sread $str)
        (repr (progn (call_with_inference_limit (Predicate (quote (eval $code $x))) 100000000) $x))))

(= (pin $x)
   PIN-SUCCESS)

(= (export! $space $file)
   (progn (write-file $file "")
          (collapse (let $x (get-atoms $space)
                         (append-file $file (repr $x))))))

!(import_prolog_function string_length)
(= (bound-space! $space $limit)
   (progn (change-state! &exportchars 0)
          (collapse (let* (($x (get-atoms $space))
                           ($y (repr $x))
                           ($l (string_length $y))
                           ($_ (change-state! &exportchars (+ (get-state &exportchars) $l))))
                          (if (> (get-state &exportchars) $limit)
                              (remove-atom $space $x) _)))))
