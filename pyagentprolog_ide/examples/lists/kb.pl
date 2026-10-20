my_length([], 0).
my_length([_|T], N) :- my_length(T, N1), N is N1 + 1.

my_reverse(L, R) :- my_reverse_acc(L, [], R).
my_reverse_acc([], Acc, Acc).
my_reverse_acc([H|T], Acc, R) :- my_reverse_acc(T, [H|Acc], R).