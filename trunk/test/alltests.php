<?php

require_once dirname(__FILE__).'/../php_support/error_handling.inc';

require_once 'PHPUnit/Framework.php';
require_once 'PHPUnit/TextUI/TestRunner.php';
require_once 'PHPUnit/Framework.php';

require_once dirname(__FILE__).'/../php_support/dbsource.inc';
require_once dirname(__FILE__).'/../php_support/mdb2_datatype.inc';

//Derive only from this testcase, other GLOBALS references will fail!
//Refer to <http://www.phpunit.de/ticket/497> which has now been fixed -- we await a new release
class TestCase extends PHPUnit_Framework_TestCase
{
	//since PHPUnit global handling is now RETARDED by default
	protected $backupGlobals = false;
	protected $createGlobalsReference = false;
}

require_once dirname( __FILE__ ) . '/gen/schema.inc';

include 'common_test.inc';
include 'dbstest_basic.inc';

class DBSchema_AllTests
{
	public static function main()
	{
		global $db_test;
		
		echo( "Running as MySQLSource...\n" );
		$db_test = new MySQLSource( 'localhost', "dbs_test", 'DBSTestUser', 'password', 'utf-8' );
		PHPUnit_TextUI_TestRunner::run(self::suite());
		
		echo( "Running as MDB2DBSource...\n" );
		@$mdb =& MDB2::factory( 
			array(
				'phptype' => 'mysqli',
				'username' => 'DBSTestUser',
				'password' => 'password',
				'hostspec' => 'localhost',
				'database' => 'dbs_test' 
				),
			array(
				//setup as utf8 for text columns
				'datatype_map' => array( 'cstring' => 'cstring' ),
				'datatype_map_callback' => array( 'cstring' => 'mdb2_cstring_utf8_callback' ),
				) 
			);
		if( @PEAR::isError( $mdb ) ) 
		{
			error_log( $mdb->getMessage() );
			die( "Unable to create MDB2 DB instance\n" );
		}
		
		$db_test = new MDB2DBSource( $mdb, 'cstring' );
		//$db_test->setFetchMode(MDB2_FETCHMODE_ASSOC);	//Just as reference, dbsource doesn't need, nor should it need it
		//check_db_error( $db_test->setCharset( 'UTF8' ) );	//hmmm??? produces an error, MySQL 5 only perhaps?!
		//$db_test->loadModule( 'Extended' );	//also not needed by dbsource
		PHPUnit_TextUI_TestRunner::run(self::suite());
	}
	
	public static function suite()
	{
		$suite = new PHPUnit_Framework_TestSuite( 'DBSChema tests' );
		$suite->addTestSuite( 'DBSTest_Clean' );
		$suite->addTestSuite( 'DBSTest_Basic' );
		return $suite;
	}
}

DBSchema_AllTests::main();

?>