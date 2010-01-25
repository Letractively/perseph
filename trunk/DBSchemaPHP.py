# ***** BEGIN LICENSE BLOCK *****
# Version: GPL 3.0
# This file is part of Persephone.
#
# Persephone is free software: you can redistribute it and/or modify it under the 
# terms of the GNU General Public License as published by the Free Software
# Foundation, version 3 of the License.
#
# Persephone is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Persephone.  If not, see <http://www.gnu.org/licenses/>.
# 
# Contributors:
#		edA-qa mort-ora-y <edA-qa@disemia.com>
# ***** END LICENSE BLOCK *****
import DBSchema
import re
import os
from string import Template
from string import atof, atol
from xml.sax.saxutils import escape as xml

##
# Add new methods to the schema objects for the PHP emitter. This of course
# makes this useless in parallel, but I don't see us ever needing t hat...
def retrofit_schema( emitter ):
	def phpName( field ):
		return emitter.memberName( field.name )
	DBSchema.Entity_Field.phpName = property( phpName )
	
	def phpMergeName( field ):
		return "_" + emitter.memberName( field.name )
	DBSchema.Entity.phpMergeName = property( phpMergeName )
		
	def phpClassName( en ):
		return emitter.className( en.name )
	DBSchema.Entity.phpClassName = property( phpClassName )
	
	def phpMemberName( self ):
		return emitter.memberName( self.name )
	
	def phpInstClassName( en ):
		if en.className != None:
			return emitter.className( en.className )
		return emitter.className( en.name )
	DBSchema.Entity.phpInstClassName = property( phpInstClassName )
	
	def phpLoadDescriptor( self, loc ):
		field = loc.getDBFieldForEntityField( self )
		return "array( '%s', '%s', '%s', $this->%s )" \
			% ( self.phpName, field.db_field.name, field.db_field.fieldType.name, self.phpName )
	DBSchema.Entity_Field.phpLoadDescriptor = phpLoadDescriptor
	
	def phpTableRef( prov, table ):
		return "array( %s'%s', '%s' )" \
			% ( "" if prov.impl.tablePrefixVar == None else "$GLOBALS['%s']." % prov.impl.tablePrefixVar, table.name, table.name );
	DBSchema.Provider.phpTableRef = phpTableRef;

#####################################################################
# The PHPEmitter takes the in-memory parsed and processed schema an emits
# the PHP code equivalent.
class PHPEmitter:
	
	def __init__( self, sc ):
		self.sc = sc
		self.base = ""
		self.out = None
		retrofit_schema( self )
		
	def emit( self, base ):
		self.base = base
		
		for entity in self.sc.entities.itervalues():
			if isinstance( entity, DBSchema.Entity_Normal ):
				self.emitFile( entity.phpClassName, lambda: self.genEntityNormal( entity ) )
			else:
				self.emitFile( entity.phpClassName, lambda: self.genEntityMerge( entity ) )
		self.emitFile( "schema", self.genSchema )
	
	def nameFor( self, name ):
		return "%s%s.inc" % (self.base, name )
	def emitFile( self, name, genFunc ):
		self.out = open( self.nameFor( name ), 'w' )
		# how is this done...
		#self.out.encoding = 'UTF-8'
		
		self.wr( "<?php /* This file was generated by Persephone. DO NOT EDIT THIS FILE! */\n" );
		self.genBaseRequires()
		genFunc()
		self.wr( "\n?>" );
		self.out.close()
		
	def genSchema( self ):
		for entity in self.sc.entities.itervalues():
			self.genRequire( entity )
		
	def genRequire( self, en, withSelf=True ):
		if withSelf:
			self.wr( "require_once dirname(__FILE__).'/%s';\n" 
				% os.path.basename( self.nameFor( en.phpClassName )  ) )
		if "PHPResolveCustomClass" in self.sc.defaults and \
			en.phpClassName != en.phpInstClassName:
			self.wr( self.sc.defaults["PHPResolveCustomClass"].replace( "%CLASS%", "%s" ) % en.phpInstClassName )
		
	def genBaseRequires( self ):
		self.wr( "require_once 'persephone/entity_base.inc';\n" );
		self.wr( "require_once 'persephone/query.inc';\n" );
		
	def genEntityNormal( self, en ):
		self.genNormalRequires( en )
		self.genEntityTypeDescriptor( en )
		self.genOpenEntityClass( en, 'Normal' )
		self.genIdentifier( en )
		
		self.genEmpty( en )
		self.genKeyCtors( en, en )
		if en.name in self.sc.mappers:
			self.genMapper( en, self.sc.mappers[en.name] )
		for search in en.searches.itervalues():
			self.genSearchInEntity( en, search )
			
		self.genCompleteEntity( en )
		
		
	def genEntityMerge( self, en ):
		self.genNormalRequires( en )
		for merge in en.keyMerges.itervalues():
			self.genRequire( merge )
			
		self.genEntityTypeDescriptor( en )
		self.genOpenEntityClass( en, 'Merge' )
		self.genIdentifier( en )
		
		self.genEmptyMerge( en )
		self.genMergeAccessors( en )
		self.genMergeSave( en )
		self.genMergeMaybeLoad( en )
		for merge in en.keyMerges.itervalues():
			self.genKeyMerge( en, merge )
			
		self.genCompleteEntity( en )
	
	def genNormalRequires( self, en ):
		for field in en.fields.itervalues():
			if isinstance( field.fieldType, DBSchema.Entity ):
				self.genRequire( field.fieldType )
							
	def genSearchesForEntity( self, en ):
		for search in self.sc.searches.itervalues():
			if search.entity == en:
				self.genSearch( search )
		
	def genMapper( self, en, loc ):
		self.genConverters( en, loc )
		self.genMaybeLoad( en, loc )
		self.genAddSave( en, loc )
		self.genEntitySearch( en, loc )
		self.genDelete( en, loc )
		
		self.wr( "//*** genMapper\n" )
		self.genGetDB( loc )

	def genKeyCtors( self, en, outerEn ):
		# Produce a convenient form of the key names for functions names and parameter lists
		keyset = en.getKeySet()
		for keys in keyset:
			keyName = ''
			keyParamStr = ''
			hasCache = False
			for i in range( len(keys) ):
				if i > 0:
					keyName += '_'
					keyParamStr += ', '
				
				keyName += keys[i].name;
				keyParamStr += "$key%d" % i
				if keys[i].phpCache != None:
					hasCache = True
			
			self.genKeyPart( en, outerEn, keys, keyName, keyParamStr, hasCache )
			
	def genGetDB( self, loc ):
		self.wr("static private function &getDB() {\n" );
		
		# Obtain the raw DB object from a var or function
		if loc.provider.impl.varName != None:
			cname = loc.provider.impl.varName
			self.wrt("""
	if( !isset( $$GLOBALS['$var'] ) )
		throw new ErrorException( "The database variable $var is not defined." );
	$$db =& $$GLOBALS['$var'];
""", { 'var': loc.provider.impl.varName } )
		else:
			cname = loc.provider.impl.funcName
			self.wrt("""
	if( !function_exists( '$func' ) )
		throw new ErrorException( "The database function $func is not defined." );
	$$db =& $func();
""", {'func': loc.provider.impl.funcName } )
		
		# Convert into DBSource if not (ie. it is MDB2)
		#NOTE: it is intentional that all entities use the same global cache of the MDB2Source
		if isinstance( loc.provider.impl, DBSchema.Provider_MDB2 ):
			self.wrt( """
	if( isset( $$GLOBALS['$mdbcache'] ) ) {
		$$mdb =& $$GLOBALS['$mdbcache'];
		$$mdb->switchMDB( $$db );	//in case it switched, but we generally don't expect that, do we?
	} else {
		$$mdb = new MDB2DBSource( $$db, '$texttype' );
		$$GLOBALS['$mdbcache'] =& $$mdb;
	}
""", { 'mdbcache': "__persephone_%s_mdbCache" % cname,
	'texttype': loc.provider.impl.textType
	 } )
			name = "mdb"
		else:
			name = "db"
			
		# return the DB object
		self.wr( "return $%s;\n}\n" % name );

		
	##########################################################
	# All the parts working on the keys of the entity -- in a mapper
	def genKeyPart( self, en, outerEn, keys, keyName, keyParamStr, hasCache ):
		self.wr( "//*** genKeyPart\n" )
		
		# setup cache string
		cache = ''
		if hasCache:
			cache = """
	if( self::getCache%s()->isCached( %s ) )
		return self::getCache%s()->getCached( %s );
""" % ( keyName, keyParamStr, keyName, keyParamStr )
	
		#Emit the finder to load from the DB (TODO: ensure only one record exists!)
		self.wrt("""
static public function findWith${keyName}( $keyParamStr ) {
	$$ret = $instName::with${keyName}( $keyParamStr );
	$$ret->find();
	return $$ret;
}

static public function findOrCreateWith${keyName}( $keyParamStr ) {
	$$ret = $instName::with${keyName}($keyParamStr);
	$$ret->findOrCreate();
	return $$ret;
}

static public function createWith${keyName}($keyParamStr) {
	$$ret = $instName::with${keyName}($keyParamStr);
	$$ret->create();
	return $$ret;
}

//create an object with the specified key (no other fields will be loaded until needed)
static public function with${keyName}($keyParamStr) {
	$cache
	$$ret = $instName::withNothing();
	$keyAssignBlock
	return $$ret;
}

""", { 'keyName': keyName, 'keyParamStr': keyParamStr,
	'keyAssignBlock': self.getKeyAssignBlock( keys ),
	'instName': outerEn.phpInstClassName,
	'cache': cache } )

	def getKeyAssignBlock( self, keys ):
		ret = ""
		for i in range( len( keys ) ):
			ret += "\t$ret->%s = $key%d;\n" % ( keys[i].phpName, i )
		return ret
		
	##################################################################
	# Produce member functions to convert all the entity types to/from db types
	def genConverters( self, en, loc ):
		self.wr( "//*** genConverters\n" )
		for field in loc.fields:
			fieldType = field.ent_field_field.fieldType if field.ent_field_field != None else field.ent_field.fieldType
			dbFuncType = field.db_convert.returnType if field.db_convert != None else field.db_field.fieldType
			entFuncType = field.ent_convert.returnType if field.ent_convert != None else fieldType
			
			#//// DB => Member
			self.wrt( "public static function _cnv_F${table}_${db_col}_T${ent_field}( $$value ) {\n",
				{ 'table': loc.table.name, 'db_col': field.db_field.name, 'ent_field': field.ent_field.name } )
			src_type = field.db_field.fieldType
			
			if field.db_convert != None:
				self.wr( "$value = %s( $value );\n" % field.db_convert.name )
				src_type = field.db_convert.returnType
			
			if dbFuncType.name != entFuncType.name:
				self.wrt( "$$value = convert_${src_type}_to_${to_type}( $$value );\n", 
					{ 'src_type': dbFuncType.name, 'to_type': entFuncType.name } )
			
			if field.ent_convert != None:
				self.wr( "$value = %s_inv( $value );\n" % field.ent_convert.name )
				
			if  field.ent_field_field != None:
				# Nulls are always converted to null, no attempt is made to instantiate target object
				# Use instance name to hook into any custom creation logic (like caching)
				self.wrt( "$$value = $$value === null ? null : $class::with${key}( $$value );\n" ,
					{ 'class': field.ent_field.fieldType.phpInstClassName, 'key': field.ent_field_field.name })
			
			self.wr( "return $value;\n" )
			self.wr( "}\n" );
			
			
			#//// Member => DB
			self.wrt( "public static function _cnv_F${ent_field}_T${table}_${db_col}( $$value ) {\n" ,
				{ 'table': loc.table.name, 'db_col': field.db_field.name, 'ent_field': field.ent_field.name } )
				
			src_type = fieldType
			if  field.ent_field_field != None:
				# As above, if we have a null we simply produce null
				self.wr( "$value = $value === null ? null : $value->%s;\n" % field.ent_field_field.phpName )
				
			if field.ent_convert != None:
				self.wr( "$value = %s( $value );\n" % field.ent_convert.name )
				src_type = field.ent_convert.returnType
				
			if dbFuncType.name != entFuncType.name:
				self.wrt( "$$value = convert_${src_type}_to_${to_type}( $$value );\n", 
					{ 'src_type': entFuncType.name, 'to_type': dbFuncType.name } )
			
			if field.db_convert != None:
				self.wr( "$value = %s_inv( $value );\n" % field.db_convert.name );
			
			
			self.wr( "return $value;\n" )
			self.wr( "}\n\n" )
			
	
	##################################################################
	# Produces the loading functions
	def genMaybeLoad( self, en, loc ):
		self.wr( "//*** genMaybeLoad\n" )
		keys = en.getRecordKeyFields()
		self.wrt("""
protected function _get_load_keys( ) {
	$$load_keys = array();
	$loadkeys;
	
	//we need some keys to load
	if( count( $$load_keys ) == 0 )
		throw new Exception( "Requires at least one alternate key to load" );
		
	return $$load_keys;
}

//public only for helpers (so search can indicate item was loaded)
public function  _set_load_keys( $$reload ) {
	if( !$$reload && $$this->_load_keys !== null )	
		throw new Exception( "Not expecting a duplicate load / not supported" );
		
	$$this->_load_keys = $$this->_get_load_keys();
}

public function _has_required_load_keys() {
	try {
		//TODO: avoid using exceptions here, may catch invalid exception!
		$$this->_get_load_keys( );
		return true;
	} catch( Exception $$ex ) {
		return false;
	}
}

protected function _maybeLoad( $$reload ) {
	$$this->_isLoading = true;
	try {
	$$this->_set_load_keys( $$reload );
	} catch( Exception $$ex ) {
		$$this->_isLoading = false;
		throw $$ex;
	}
		
	$$ret = dbs_dbsource_load( 
		self::getDB(),
		$table,
		$$this, 
		$$this->_load_keys,
		$members
		);
	$$this->_isLoading = false;	//TODO: should we catch exceptions and turn this off as well??
	if( !$$ret ) {
		$$this->_load_keys = null;	//reset these keys as we didn't actually load
		return false;
	}
	$cache
	return true;
}
""", { 
			'loadkeys': self.getKeyBlock( loc.fields, False, lambda key:
				"$load_keys[] = %s;" % key.phpLoadDescriptor(loc) ),
			'table': loc.provider.phpTableRef( loc.table ),
			'members': self.getFields( self.FOR_LOAD, loc.fields ),
			'cache': self.getAddToCache( en )
			} )
				

	def getPHPArrayStr( self, tuples ):
		buf = "array(\n"
		buf += ",\n".join( tuples )
		buf += "\n)\n"
		return buf
	
	def getPHPMapArrayStr( self, tuples ):
		return self.getPHPArrayStr( [ "'%s' => %s" % ( t, tuples[t] ) for t in tuples ] )
	
	def genAddSave( self, en, loc ):
		self.wr( "//*** genAddSave\n" )
		keys = en.getRecordKeyFields()
		self.wrt("""
	
protected function getSaveKeys( $$adding ) {
	$$keys = array();
	$savekeys;
	return $$keys;
}

protected function _save( $$adding ) {

	//use the same keys as loading to allow for modifying key fields
	if( $$this->_load_keys !== null )
		$$usekeys = $$this->_load_keys;
	else
		$$usekeys = $$this->getSaveKeys( $$adding );
	
	//check that no read-only fields have been modified
	$readonly
	
	dbs_dbsource_save( 
		self::getDB(),
		$table,
		$$this,
		$$usekeys,
		$members,
		$insertField
		);
	$$this->_status = DBS_EntityBase::STATUS_EXTANT;
	//now reclaculate keys in case a load field was changed, or some default set
	//NOTE: we are no longer in "adding" mode here!
	$$this->_load_keys = $$this->getSaveKeys( false );
	$cache
}""", {
		'savekeys': self.getKeyBlock( loc.fields, True, lambda key:
				"$keys[] = %s;" % key.phpLoadDescriptor(loc) ),
		'readonly': self.getCheckReadOnly( loc.fields ),
		'table': loc.provider.phpTableRef( loc.table ),
		'members': self.getSaveMembers( loc.fields ),
		'insertField': self.getInsertFields( loc.fields ),
		'cache': self.getAddToCache( en )
		} )
		
		
	# Updates the cache when, used when an item is saved or loaded
	# we have to check if the key field name is defined first since in some
	# cases it may not be (incomplete data, or alternate keys)
	def getAddToCache( self, en ):
		buf = ""
		# check for cached keys
		for field in en.fields.itervalues():
			if field.phpCache != None:
				buf += "if( $this->__has( '%s' ) )" % field.phpName
				buf += "self::getCache%s()->add( $this->%s, $this );\n" % ( field.name, field.phpName )
				
		return buf
	
	def getInsertFields( self, fields ):
		for field in fields:
			if not field.isPersistLoad():
				continue
			if field.db_field.lastInsert:
				return "array( %s )" % self.dbField( field )
		
		return "null"
		
	def getCheckReadOnly( self, fields ):
		buf = ""
		for i in range( len( fields ) ):
			if fields[i].isPersistSave():
				continue
			buf += "\tif( $this->__isDirty('%s') )\n" % fields[i].ent_field.phpName
			buf += "\t\tthrow new DBS_FieldException( '%s', DBS_FieldException::SAVE_LOAD_ONLY );\n" % fields[i].ent_field.phpName
		return buf
		
	def getSaveMembers( self, fields ):
		mem = []
		for field in fields:
			if not field.isPersistSave():	#//for safety just don't save such fields
				continue;
 			mem.append( self.dbField( field ) )
		return self.getPHPArrayStr( mem )
					
	def genEntitySearch( self, en, loc ):
		self.wr( "//*** genEntitySearch\n" )
		self.wrt("""
/**
 * Obtains an iterable form of the results. They are to be loaded only on demand...
 * This accepts a variable number of parameters for the query options/conditions.
 */
static public function search( ) {
	$args
	
	return dbs_dbsource_search( 
		self::getDB(),
		$table,
		'_${class}_privConstruct',
		$searchfields,
		$loadfields,
		$$args	//pass all options to loader
		);
}
		""",{
			'args': self.args_or_array( ),
			# In some cases the loadfields are not the same as the search fields, this generally only applies
			# in situations with "save only" persistence
			'searchfields': self.getFields( self.FOR_SEARCH, loc.fields ),
			'loadfields': self.getFields( self.FOR_LOAD, loc.fields ),
			'table': loc.provider.phpTableRef( loc.table ),
			'class': en.phpInstClassName,
			})
			
	FOR_SEARCH = 1
	FOR_LOAD = 2
	
	def getFields( self, forWhat, fields ):
		mem = []
		for field in fields:
			if forWhat == self.FOR_LOAD and not field.isPersistLoad():
				continue;
			mem.append( self.dbField( field ) )
		return self.getPHPArrayStr( mem )
	
	def genDelete( self, en, loc ):
		self.wr( "//*** genDelete\n" )
		self.wrt("""
/**
 * Deletes all items matching the provided query.
 */
static public function searchAndDelete( ) {
	$args
	return self::_searchAndDelete( $$args );
}

static private function _searchAndDelete( $$args ) {

	return dbs_dbsource_delete( 
		self::getDB(),
		$table,
		'_${class}_privConstruct',
		$fields,
		$$args	//pass all options to deleter
		);
}

//TODO: as with everything, support multiple locators
public function delete() {
	$$query = array();
	$limitPart;
	$$keys = array();
	$deletekeys
	
	if( count( $$keys ) == 0 )
		throw new Exception( "No key specified for delete" );
		
	$$query[] = count( $$keys ) > 1 ? DBS_Query::matchAndGroup( $$keys ) : $$keys[0];
	
	$$this->_searchAndDelete( $$query );
		
	$$this->_status = DBS_EntityBase::STATUS_DELETED;
}
	""", {
		'args': self.args_or_array( ),
		'fields': self.getFields( self.FOR_SEARCH, loc.fields ),
		'table': loc.provider.phpTableRef( loc.table ),
		'class': en.phpInstClassName,
		'deletekeys': self.getKeyBlock( loc.fields, False, lambda field:
			"\t\t$keys[] = DBS_Query::match( '%s', $this->%s );\n" % ( field.phpName, field.phpName ) ),
		# TODO: abstract this into the delete command -- there is a way to do this postgres as well (see entity_base.inc delete)
		'limitPart': '$query[] = DBS_Query::limit( 1 );	//a safety measure' if loc.provider.dbType == 'mysql' else ''
		} )
		
	
	def genMergeSave( self, en ):
		self.wr( """//*** genMergeSave
function _save( $adding ) {
""")
		# TODO: Define an handle what happens on partial saves
		# TODO: variable propogation
		for merge in en.merges.itervalues():
			self.wr( 
				self._if( 
					"$this->%s->__isAnythingDirty()" % merge.phpMergeName,
					"$this->%s->_save( $adding );\n" 	% merge.phpMergeName
					)
				)
			
		self.wr( """
	$this->_status = DBS_EntityBase::STATUS_EXTANT;
}
""")

	def genKeyMerge( self, entity, merge ):
		self.genKeyCtors( merge, entity )
		
	def genMergeMaybeLoad( self, en ):
		self.wr( """//*** getMergeMaybeLoad
function _maybeLoad( $reload ) {
			$ret = true;
""")
		#TODO: handle mismatch in return values
		for merge in en.merges.itervalues():
			self.wr( "$ret &= $this->%s->maybeLoad( $reload );\n" % merge.phpMergeName );
			
		self.wr( self.getAddToCache( en ) )
		self.wr( "return $ret;\n}\n" );
		
	##################################################################
	# The Nothing constructors 
	def genEmpty( self, en ):
		self.wr( "//*** genEmpty\n" )
		self.wrt("""
static public function withNothing() {
	$$ret = new $class();
	return $$ret;
}

static public function createWithNothing() {
	$$ret = new $class();
	$$ret->create();
	return $$ret;
}
		""", { 'class': en.phpInstClassName } )
		
	def genEmptyMerge( self, en ):
		self.wr( "//*** genEmpty\n" )
		self.wrt("""
static public function withNothing() {
	$$ret = new $class();
	$mergeWith
	return $$ret;
}

static public function createWithNothing() {
	$$ret = new $class();
	$mergeCreate
	$$ret->_status = DBS_EntityBase::STATUS_NEW;
	return $$ret;
}
		""", { 
		'class': en.phpInstClassName,
		'mergeWith': 
			"\n".join([ 
				"$ret->%s = %s::withNothing();	$ret->%s->maybeLoadCallback = array( $ret, 'maybeLoad%s' );	$ret->%s->backModifiedCallback = array( $ret, 'mergeBackModified%s' );"
					% (merge.phpMergeName, merge.phpClassName, merge.phpMergeName, merge.phpClassName, merge.phpMergeName, merge.phpClassName ) 
				for merge in en.merges.itervalues() 
				]),
		'mergeCreate': 
			"\n".join([ 
				"$ret->%s = %s::createWithNothing();	$ret->%s->maybeLoadCallback = array( $ret, 'maybeLoad%s' );	$ret->%s->backModifiedCallback = array( $ret, 'mergeBackModified%s' );"
					% (merge.phpMergeName, merge.phpClassName, merge.phpMergeName, merge.phpClassName, merge.phpMergeName, merge.phpClassName ) 
				for merge in en.merges.itervalues() 
				]),
		 } )
	##################################################################
	#  The identifier get and ctro
	# FEATURE: if there is only one key, or a simpler form, then use that -- having
	# this serialized form is excessive in most cases
	def genIdentifier( self, en ):
		self.wr("//*** genIdentifier\n" );
		self.wr("""
static public function withIdentifier( $ident ) {
	$entity = self::withNothing();
""" )
		
		if en.getSingleKey() == None:
			self.wr("""
	$data = @unserialize( $ident );
	if( $data === false ) {
		""");
			# we may have the identifier at this point
			if en.identifierField != None:
				# TODO: wrap type exceptions as some kind of identifier exception
				self.wr( "$raw = $ident; %s" % self.serialOutFunc( en.identifierField ) )
				self.wr( "return $entity;\n" );
			# otherwise just an exception
			self.wr( "throw new Exception( 'Invalid identifier' ); }\n")
			
			for key in en.getRecordKeyFields():
				self.wr( self._if(
					"array_key_exists( '%s', $data )" % key.phpName,
					"$raw = $data['%s']; %s\n" % ( key.phpName, self.serialOutFunc( key ) )
					) )
		else:
			# With a single key we know we never have serialized data
			self.wr( "$raw = $ident; %s" % self.serialOutFunc( en.identifierField ) )
			
		self.wr( "return $entity; }\n" );
	
		# The any identifier just uses what fields are available to identify the key
		# more than one may exist for an entity
		self.wr( "public function getAnyIdentifier() {" );
		if en.getSingleKey() != None:
			self.wr( "return $this->getIdentifier();\n}\n" );
		else:
			self.wr( "$entity = $this;\n" );
			buf = "$data = array();\n"
			for key in en.getRecordKeyFields():
				buf += self._if(
					self._this_has( key ),
					"$data['%s'] = %s;\n" % ( key.phpName, self.serialInFunc( key ) )
					)
			self.wr( buf );
			self.wr( "return serialize( $data );\n}\n" );

		# There is only one solo identifier for any object, it is the one that best matches
		# user's expectations so is simply called identifier
		self.wr( "public function getIdentifier() {" );
		self.wr( "$entity = $this;\n" );
		if en.identifierField != None:
			self.wr( "return %s;" % self.serialInFunc( en.identifierField ) )
		else:
			buf = "$data = array();\n"
			for key in en.getRecordKeyFields():
				buf += "$data['%s'] = %s;\n" % ( key.phpName, self.serialInFunc( key ) )
			self.wr( buf );
			self.wr( "return serialize( $data );" )
			
		self.wr("\n}\n" )
		
	##################################################################
	# 
	def genEntityTypeDescriptor( self, en ):
		self.wrt( """
//*** genEntityTypeDescriptor		
class ${class}TypeDescriptor extends DBS_TypeDescriptor {
	public $$options = array(
		'titleField' => $titleField,
		);
""", { 'class': en.phpClassName,
	'titleField': "'%s'" % en.titleField.phpName if en.titleField != None else 'null' } )
		
		##
		self.wr( "\npublic $names = array(\n" )
		for field in en.fields.itervalues():
			self.wrt(
"""'$name' => array( $nonbasetype, $basetype, $options ),
			""", { 
				'name': field.phpName,
				'nonbasetype': 'null'  if field.fieldType.baseType() else "'%s'" % field.fieldType.name,
				'basetype': "'%s'" % field.fieldType.getRootType().name ,
				'options': self.getFieldOptions( en, field )
				} )
		self.wr( ');\n' )
		
		##
		self.wr( "\npublic $defaults = array(\n" )
		for field in en.fields.itervalues():
			if not field.hasDefault:
				continue
			self.wrt("""	'$name' => $const,
				""", {
					'name': field.phpName,
					'const': self.constantExpr( field.fieldType, field.defaultValue )
				} )
		self.wr( ');\n' )
				
		##
		self.wr( "\npublic $aliases = array(\n" )
		for alias in en.aliases.iteritems():
			self.wrt("""	'$alias' => '$name',\n""", {
				'alias': self.memberName(alias[0]),
				'name': self.memberName(alias[1]) } )
		self.wr( ');\n' )
		
		##
		# Produce the checkType function. This produces a switch statement on
		# the field name and checks the type of the field in the case block.
		self.wr( """	
	public function checkType( $field, $value ) {
		switch( $field ) {
		""")
		for field in en.fields.itervalues():
			name = "'%s'" % field.phpName
			tname = field.fieldType.name
			
			self.wr( "case %s:\n" % name )
			self.wr( self._if( 
				"$value === null",
				"break;" if field.allowNull else self._throwSetFieldException( field, 'TYPE_NULL' ) 
				) )
				
			if tname == 'Integer' or tname == 'Float' or tname == 'Decimal':
				self.wr( self._if( 
					"!is_numeric( $value )",
					self._throwSetFieldException( field, 'TYPE_NUMERIC' )
					) )
			elif tname == 'String' or tname == 'Text':
				self.wr( self._if(
					"!is_convertible_to_string($value)",
					self._throwSetFieldException( field, 'TYPE_STRING' )
					) )
				if field.maxLen != None:
					self.wr( self._if(
						"strlen( $value ) > %d" % field.maxLen,
						self._throwSetFieldException( field, 'TYPE_LEN' )
						) )
			elif tname == 'Date' or tname == 'DateTime':
				self.wr( self._if(
					"!($value instanceof DateTime)",
					self._throwSetFieldException( field, 'TYPE_DATE' )
					) )
			
			elif isinstance( field.fieldType, DBSchema.Entity ):
				self.wr( self._if(
					"!($value instanceof %s)" % field.fieldType.phpInstClassName,
					self._throwSetFieldException( field, 'TYPE_ENTITY' )
					) )
				
						
			self.wr( "\tbreak;\n" );
		self.wrt("""
		}
	} //end checkType
	
} //end class
		""", { 'class': en.phpClassName } )
	
	def getFieldOptions( self, en, field ):
		options = {}
		if field.maxLen != None:
			options['maxLength'] = '%d' % field.maxLen
		options['label'] = "'%s'" % field.label
		options['trueName'] = "'%s'" % field.name
		
		return self.getPHPMapArrayStr( options )
		
	##################################################################
	# Merge Accessors
	def genMergeAccessors( self, en ):
		# TODO: getRef?
		# TODO: identifier get
		# get -----------------------------------------------------
		self.wr( "public function __get( $field ) {\n" )
		for merge in en.merges.itervalues():
			self.wr( self._if( "$this->%s->__defined( $field )" % merge.phpMergeName, 
				"return $this->%s->__get( $field );" % merge.phpMergeName ) );
		self.wr( "\tthrow new DBS_FieldException( $field, DBS_FieldException::UNDEFINED );\n\t}\n" )

		# set -----------------------------------------------------
		self.wr( "public function __set( $field, $value ) {\n" )
		for merge in en.merges.itervalues():
			self.wr( self._if( "$this->%s->__defined( $field )" % merge.phpMergeName, 
				"$this->%s->__set( $field, $value );\nreturn;\n" 
					% merge.phpMergeName ) )
		self.wr( "\tthrow new DBS_FieldException( $field, DBS_FieldException::UNDEFINED );\n\t}\n" )
		
		# forwarding fields --------------------------------------
		for merge in en.merges.itervalues():
			
			# Back-loading and maybeLoad hook
			# TODO: only goes back one step, could in theory require two steps
			self.wr( "private function backLoad%s() {\n" % merge.phpClassName )
			for lsPair in en.linksWithEntity( merge ):
				for link in lsPair[0]:
					if link.entity == merge:
						continue
					self.wr( "if( $this->%s->isUnknown() && $this->%s->_has_required_load_keys() )\n" 
						% ( link.entity.phpMergeName, link.entity.phpMergeName ) )
					self.wr( "\t$this->%s->find();\n" % link.entity.phpMergeName );
			self.wr( "}\n" );
			self.wrt( """
protected function maybeLoad$class() {
	//if enough is available to load, then we don't need to intercept
	if( $$this->$merge->_has_required_load_keys() )
		return;
	
	$$this->backLoad$class();
}
""", { 'class': merge.phpClassName,
		'merge': merge.phpMergeName
		 } )
		
			# merge back modified (why does this need to be protected and not private?)
			self.wr( "protected function mergeBackModified%s( $fields ) {\n" % merge.phpClassName )
			for lsPair in en.linksWithEntity( merge ):
				self.wr( "if( array_search( '%s', $fields ) !== false ) {\n" % lsPair[1].field.phpName )
				self.wr( "\t$value = $this->%s->%s;\n" % (merge.phpMergeName, lsPair[1].field.phpName ) )
				for link in lsPair[0]:
					if link.entity == merge:
						continue
					self.wr( "\t$this->%s->%s = $value;\n" % ( link.entity.phpMergeName, link.field.phpName ) )
				self.wr( "}\n" )
			self.wr( "}\n" )
			
	##################################################################
	# Open Class
	def genOpenEntityClass( self, en, type ):
		self.wrt("""
class $class extends DBS_${type}EntityBase {
	static private $$_typeDescriptor;

	static public function getTypeDescriptor() {
		if( self::$$_typeDescriptor == null )
			self::$$_typeDescriptor = new ${class}TypeDescriptor();
		return self::$$_typeDescriptor;
	}
	
	protected function __construct() {
		$$this->_data_type = self::getTypeDescriptor();
		parent::__construct();
	} 
	
	static public function _privConstruct() {
		$$item = new $inst();
		return $$item;
	}
"""	, {'class': en.phpClassName,
		'inst': en.phpInstClassName,
		'type': type
		} )
	
		# Create merge declarations
		if type == 'Merge':
			for merge in en.merges.itervalues():
				self.wr("\tprotected $%s; //<%s>\n" % ( merge.phpMergeName, merge.phpClassName ) )
				
		# Create cache declarations
		for field in en.fields.itervalues():
			if field.phpCache == None:
				continue
			self.wrt("""
	static private $$_cache$key;
	
	static public function getCache$key() {
		if( self::$$_cache$key == null )
			self::$$_cache$key =  new $create( $params );
		return self::$$_cache$key;
	}
		
""", { 'key': field.name,
			'create' : field.phpCache[0],
			'params' : ",".join( [ "'%s'" % p for p in field.phpCache[1:] ] )

		} )

	#################################################
	# Close class
	def genCloseEntityClass( self, en ):
		self.wrt( """} //end of class

function _${inst}_privConstruct() {
	return ${inst}::_privConstruct();
}

""", { 'class': en.phpClassName,
		'inst': en.phpInstClassName	} )
		
	def genCompleteEntity( self, en ):
		self.genCloseEntityClass( en )
		# require ourself in case we're a custom class
		self.genRequire( en, False )
		# Add searches related to this entity
		self.genSearchesForEntity( en )
		
		
	##
	# Creates the PHP fragment to take a value from the entity and prepare it for
	# for form.
	# TODO: Handle nulls in sub field references
	def serialInFunc( self, ent ):
		if isinstance( ent.fieldType, DBSchema.Entity ) or	ent.fieldType.getRootType().name == 'Entity':	# Allow type masquerading (TODO: formalize this)
			sub = '->identifier' #+ self.memberName( link.name )
		else:
			sub = ''
				
		return "$entity->%s%s"	% ( ent.phpName, sub )
	
	##
	# Creates the PHP fragment to take a value from the form and convert it to
	# the entity field type.
	def serialOutFunc( self, ent ):
		# when referencing objects we'll use the lazy loading "withNothing"
		if isinstance( ent.fieldType, DBSchema.Entity ):
			sub = 'unset($ent); $ent = ' + ent.fieldType.phpClassName + "::withIdentifier( $raw );\n"
			assign = '= $ent'
		elif ent.fieldType.getRootType().name == 'Entity':	# Allow type masquerading (TODO: formalize this)
			sub = 'unset($ent); $ent = ' + self.className( ent.name ) + "::withIdentifier( $raw );\n"
			assign = '= $ent'
		else:
			assign = '= $raw'
			sub = ''
		
		buf = sub
		buf += "$entity->%s %s;\n" % ( ent.phpName, assign )
		return buf
		
	#/***************************************************************************
	#* Search Generation
	#***************************************************************************/	
	def genSearch( self, search ):
		self.wr( "class %s {\n\tstatic public function search" % self.className( search.name ) )
		self.genSearchInner( search, None )
		self.wr( "}\n" )
	
	def genSearchInEntity( self, en, search ):
		if search.static:
			self.wr( "static " )
		self.wr( "public function %s" % self.memberName( search.name ) )
		self.genSearchInner( search, en )
	
	def genSearchInner( self, search, entity ):
		self.wr( "(" )
		for i in range( search.placeholderCount ):
			if i > 0:
				self.wr( ", " )
			self.wr( "$p%d" % i )
		self.wr( ") { \n" )
		self.wr( "\treturn %s::search(\n" % search.entity.phpClassName );
		
		params = []
		if search.filter != None:
			params.append( self.genSearchFilter( search, search.filter ) )
		else:	# without a filter assume full matching
			params.append( "DBS_Query::matchAll()" );
			
		if search.sort != None:
			params.append( self.genSearchSort( search, search.sort ) )
			
		self.wr( ",".join( params ) )
		self.wr( "\t);\n" );
		
		self.wr( "}\n" )
	
	groupMap = {
		'AND': 'And',
		'OR': 'Or',
		}
	def genSearchFilter( self, search, filter ):
		if isinstance( filter, DBSchema.Search_FilterFieldOp ) or isinstance( filter, DBSchema.Search_FilterFieldPattern):
			if filter.placeholder != None:
				#TODO: this will likely cause problems for placeholder ordering
				expr = "$p%d" % filter.placeholder
			elif filter.containerRef != None:
				if isinstance( filter.containerRef, DBSchema.Entity ):
					if( filter.containerRef.name != search.container.name ):
						raise Exception, "ContainerRef is expected to be the Container itself: %s != %s" % (filter.containerRef.name, search.container.name )
					expr = "$this";
				else:	#Entity_Field
					expr  = "$this->%s" % filter.containerRef.phpName
			else:
				expr = self.constantExpr( filter.field.fieldType, filter.const )
				
			if isinstance( filter, DBSchema.Search_FilterFieldPattern):
				return "DBS_Query::matchStringPattern( '%s', %s )" \
					% ( filter.field.phpName, expr )
			else:
				return "DBS_Query::match( '%s', %s, '%s' )" \
					% ( filter.field.phpName, expr, filter.op )
					
		if isinstance( filter, DBSchema.Search_FilterGroupOp ):
			op = self.groupMap[filter.op]
			expr = "DBS_Query::match%sGroup(" % op
			expr += ",".join( [ self.genSearchFilter( search, sub ) for sub in filter.exprs ] )
			expr += ")"
			return expr
		
	def genSearchSort( self, search, sort ):
		cols = [ "'%s'" % field.phpName for field in sort.fields]
		return "DBS_Query::sort( %s, DBS_Query::%s )" \
			% ( self.getPHPArrayStr( cols ), 
				"SORT_ASC" if sort.dir == 'ASC' else "SORT_DESC" )
		
		

	##################################################################
	# Output functions
	# The short names are since they must always be preceded with "self." and I
	# need to call them very often.
	
	def wrt( self, tpl, params ):
		self.wr( Template( tpl ).substitute( params ) )
		
	def wr( self, data ):
		self.out.write( data )
		
		
	##################################################################
	# PHP Language Constructs
			
	##
	# looks through "this" for keys and outputs code to collect all of those
	# keys via a provided statement
	#
	# NOTE: To deal with standard DB practice of allowing duplicate NULL values
	# in Key fields, something of type KEY_TYPE_ALT with a NULL value will not
	# be considered a key.  This does not apply to KEY_TYPE_RECORD since in
	# that case the combined key must be unique, not the individual column.
	#
	# @param fields [in] the fields to consider for keys
	# @param checkAdding [in] allow that load only fields to be absent if "$adding" is true
	# @param statement [in] assignment statement for each key
	def getKeyBlock( self, fields, checkAdding, statement ):
		buf = "";
		#only need one ALT_RECORD_KEY, but need all RECORD_KEY
		for field in fields:
			key = field.ent_field
			if key.keyType == DBSchema.KEY_TYPE_NONE:
				continue;
				
			if key.keyType == DBSchema.KEY_TYPE_RECORD:
				_else = self._throwFieldException( key, "MISSING_REQ" )
				if checkAdding and field.isLoadOnly():	#TODO: check LAST_INSERT_ID, but see comment in test schema first!
					_else = self._if( '!$adding',	_else )
				buf += self._if(
					self._this_has( key ),
					statement( key ),
					_else
					)
			elif key.keyType == DBSchema.KEY_TYPE_ALT:
				buf += self._if(
						self._this_has( key ),
						self._if(
							"$this->%s !== null" % key.phpName,
							statement( key )
						)
					)
			else:
				raise Exception, "Unsupported key type in entity:  %s " % key.name
		
		return buf;
	
	def _if( self, cond, block, elseblock = None ):
		buf = "\n\tif( %s ) { \n\t\t%s\n\t}\n" % ( cond, block )
		if elseblock != None:
			buf += "\telse {\n%s\n\t}\n" % elseblock
		return buf
	
	def _this_has( self, field ):
		return "$this->__has('%s')" % field.phpName
	
	def _throwFieldException( self, field, extype ):
		return "throw new DBS_FieldException( '%s', DBS_FieldException::%s );" % ( field.phpName, extype )
	def _throwSetFieldException( self, field, extype ):
		return "throw new DBS_SetFieldException( '%s', DBS_SetFieldException::%s );" % ( field.phpName, extype )
	
	##
	# Produces the literal constant expression for a value of a given type
	# TODO: Should this not be part of the processor?
	def constantExpr( self, fieldType, value ):
		tname = fieldType.name
		# Handle null values
		if value == None:
			return 'null';
		
		if tname == 'String' or tname =='Text':
			return "'%s'" % self.addslashes( value )
		elif tname == 'Integer':
			return "%d" % atol( value )
		elif tname == 'Float' or tname == 'Decimal':
			return "%f" % atof( value )
		elif tname == 'Bool':
			if value == 'True':
				return True
			if value == 'False':
				return False
			raise Exception, "Invalid Bool value for constant %s => %s"  % ( tname, value )
		else:
			raise Exception, "Unknown type for constant %s " % tname
		
	##
	# like the PHP function of the same name
	def addslashes( self, text ):
		return re.sub('''(['"\\$])''', r'\\\1', text )
		
	##
	# Produces the className for an etitty
	def className( self, str ):
		return str[0:1].upper() + str[1:]
	
	def memberName( self, str ):
		#replace all first caps except last before non-cap
		# treat numbers as caps to avoid things like MD5Hash => mD5Hash
		
		#all caps  Ex: UPPER => upper
		#PYTHON: if re.match( '(?u)^\P{Lu}+$', str ):
		if re.search('(?u)^[A-Z0-9]+$', str ):
			return str.lower()
		
		#one leading cap  Ex: BasicName => basicName
		#PYTHON: ^(\p{Lu})([^\p{Lu}].*)$
		m = re.search( '^([A-Z0-9])([^A-Z0-9].*)$', str )
		if m:
			return m.group(1).lower() + m.group(2)
			
		#many leading caps Ex: IDString => idString
		#PYTHON: ^(\p{Lu}+)(\p{Lu}[^\p{Lu}])
		m = re.search( '^([A-Z0-9]+)([A-Z0-9][^A-Z0-9].*)$', str )
		if not m:
			raise Exception, "Unconvertable member: %s " % str
		return m.group(1).lower() + m.group(2)

	def dbField( self, field ):
		return "array( '%s', '%s', '%s' )" % (field.ent_field.phpName, field.db_field.name, field.db_field.fieldType.name)
	
	def args_or_array( self ):
		#//allow an array to be used instead of variable arguments
		return '$args = func_get_args();	\
			if( count( $args ) === 1 && is_array( $args[0] ) )\
				$args = $args[0];\
			'

	# End of PHP Language Constructs
	##################################################################
	