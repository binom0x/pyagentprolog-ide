max(X, Y, X) :- X >= Y, !.
max(_, Y, Y).

classify(X, positive) :- X > 0, !.
classify(X, negative) :- X < 0, !.
classify(_, zero).

sign(X, S) :- X > 0 -> S = positive ;
              X < 0 -> S = negative ;
              S = zero.