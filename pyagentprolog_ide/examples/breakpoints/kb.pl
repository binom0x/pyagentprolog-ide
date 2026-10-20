loop(0) :- !.
loop(N) :- N > 0, N1 is N - 1, loop(N1).

run_loop :- loop(5).