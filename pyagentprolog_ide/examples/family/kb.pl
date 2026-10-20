parent(ivan, alexey).
parent(ivan, maria).
parent(alexey, petr).
parent(alexey, anna).
parent(maria, sergey).

grandparent(X, Z) :- parent(X, Y), parent(Y, Z).
ancestor(X, Y) :- parent(X, Y).
ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).