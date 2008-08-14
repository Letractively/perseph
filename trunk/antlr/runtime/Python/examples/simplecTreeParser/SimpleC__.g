lexer grammar SimpleC;
options {
  language=Python;

}

T21 : ';' ;
T22 : '(' ;
T23 : ',' ;
T24 : ')' ;
T25 : '{' ;
T26 : '}' ;

// $ANTLR src "SimpleC.g" 91
FOR : 'for' ;
// $ANTLR src "SimpleC.g" 92
INT_TYPE : 'int' ;
// $ANTLR src "SimpleC.g" 93
CHAR: 'char';
// $ANTLR src "SimpleC.g" 94
VOID: 'void';

// $ANTLR src "SimpleC.g" 96
ID  :   ('a'..'z'|'A'..'Z'|'_') ('a'..'z'|'A'..'Z'|'0'..'9'|'_')*
    ;

// $ANTLR src "SimpleC.g" 99
INT :	('0'..'9')+
    ;

// $ANTLR src "SimpleC.g" 102
EQ   : '=' ;
// $ANTLR src "SimpleC.g" 103
EQEQ : '==' ;
// $ANTLR src "SimpleC.g" 104
LT   : '<' ;
// $ANTLR src "SimpleC.g" 105
PLUS : '+' ;

// $ANTLR src "SimpleC.g" 107
WS  :   (   ' '
        |   '\t'
        |   '\r'
        |   '\n'
        )+
        { $channel=HIDDEN }
    ;    
