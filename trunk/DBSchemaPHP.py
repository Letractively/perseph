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
		
	def phpClassName( en ):
		return emitter.className( en.name )
	DBSchema.Entity.phpClassName = property( phpClassName )
	DBSchema.Form.phpClassName = property( phpClassName )
	DBSchema.Listing.phpClassName = property( phpClassName )
	
	def phpMemberName( self ):
		return emitter.memberName( self.name )
	DBSchema.Form_Field.phpMemberName = property( phpMemberName )
	
	def phpInstClassName( en ):
		if en.className != None:
			return emitter.className( en.className )
		return emitter.className( en.name )
	DBSchema.Entity.phpInstClassName = property( phpInstClassName )
	
	def phpLoadDescriptor( self, loc ):
		field = loc.getDBFieldForEntityField( self )
		return "array( '%s', '%s', $this->%s )" \
			% ( field.db_field.name, field.db_field.fieldType.name, self.phpName )
	DBSchema.Entity_Field.phpLoadDescriptor = phpLoadDescriptor
	
	def phpFormName( en ):
		return emitter.formNameOf( en )
	DBSchema.Entity_Field.phpFormName = property( phpFormName )
	
	def phpFormLabel( en ):
		return emitter.formLabelOf( en )
	DBSchema.Entity_Field.phpFormLabel = property( phpFormLabel )
	
	def phpTableRef( prov, table ):
		return "array( %s'%s', '%s' )" \
			% ( "" if prov.tablePrefixVar == None else "$GLOBALS['%s']." % prov.tablePrefixVar, table.name, table.name );
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
		self.emitFile( "schema", self.genSchema )
		
		for form in self.sc.forms.itervalues():
			self.emitFile( form.name + ".form", lambda: self.genForm( form ) )
		
		for listing in self.sc.listings.itervalues():
			self.emitFile( listing.name + ".listing", lambda: self.genListing( listing ) )
	
	def emitFile( self, name, genFunc ):
		fullname = "%s%s.inc" % (self.base, name )
		self.out = open( fullname, 'w' )
		# how is this done...
		#self.out.encoding = 'UTF-8'
		
		self.wr( "<?php\n/* This file was generated by Persephone. DO NOT EDIT THIS FILE! */\n?>\n" )
		genFunc()
		self.out.close()
		
	def genSchema( self ):
		self.wr( "<?php\n" );
		self.genBaseRequires()
		for entity in self.sc.entities.itervalues():
			self.genEntity( entity )
		self.wr( "\n?>" );
		
	def genBaseRequires( self ):
		self.wr( "require_once 'persephone/entity_base.inc';\n" );
		self.wr( "require_once 'persephone/query.inc';\n" );
		
	def genEntity( self, en ):
		self.genOpenEntityClass( en )
		self.genEntityDataTypes( en )
		if en.name in self.sc.mappers:
			self.genMapper( en, self.sc.mappers[en.name] )
		self.genCloseEntityClass( en )
		
	def genMapper( self, en, loc ):
		self.genConverters( en, loc )
		self.genMaybeLoad( en, loc )
		self.genAddSave( en, loc )
		self.genSearch( en, loc )
		self.genDelete( en, loc )
		self.genEmpty( en, loc )
		
		self.wr( "//*** genMapper\n" )
		self.wrt("""
static private function &getDB() {
	if( !isset( $$GLOBALS['$var'] ) )
		throw new ErrorException( "The database variable $var is not defined." );
	return $$GLOBALS['$var'];
}
""", { 'var': loc.provider.varname } )

		# Produce a convenient form of the key names for functions names and parameter lists
		keyset = en.getKeySet()
		for keys in keyset:
			keyName = ''
			keyParamStr = ''
			for i in range( len(keys) ):
				if i > 0:
					keyName += '_'
					keyParamStr += ', '
				
				keyName += keys[i].name;
				keyParamStr += "$key%d" % i
			
			self.genKeyPart( en, loc, keys, keyName, keyParamStr )
			
	##########################################################
	# All the parts working on the keys of the entity -- in a mapper
	def genKeyPart( self, en, loc, keys, keyName, keyParamStr ):
		self.wr( "//*** genKeyPart\n" )
		#Emit the finder to load from the DB (TODO: ensure only one record exists!)
		self.wrt("""
static public function &findWith${keyName}( $keyParamStr ) {
	$$ret =& self::with${keyName}( $keyParamStr );
	
	if( !$$ret->_maybeLoad() )
		throw new Exception( "Failed to find a record ($keyName) / ($keyParamStr)" );
	$$ret->_status = DBS_EntityBase::STATUS_EXTANT;
		
	return $$ret;
}

static public function &findOrCreateWith${keyName}( $keyParamStr ) {
	$$ret =& self::with${keyName}($keyParamStr);
	
	if( $$ret->_maybeLoad() )
		$$ret->_status = DBS_EntityBase::STATUS_EXTANT;
	else
		$$ret->_status = DBS_EntityBase::STATUS_NEW;
	
	return $$ret;
}

static public function &createWith${keyName}($keyParamStr) {
	$$ret =& self::with${keyName}($keyParamStr);
	$$ret->_status = DBS_EntityBase::STATUS_NEW;
	return $$ret;
}

//create an object with the specified key (no other fields will be loaded until needed)
static public function &with${keyName}($keyParamStr) {
	$$ret = new $instClassName();
	$keyAssignBlock
	return $$ret;
}

""", { 'keyName': keyName, 'keyParamStr': keyParamStr,
	'instClassName': en.phpInstClassName,
	'keyAssignBlock': self.getKeyAssignBlock( keys ) } )

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
			#//// DB => Member
			self.wrt( "public static function _cnv_F${table}_${db_col}_T${ent_field}( $$value ) {\n",
				{ 'table': loc.table.name, 'db_col': field.db_field.name, 'ent_field': field.ent_field.name } )
			src_type = field.db_field.fieldType
			
			if field.db_convert_func != None:
				self.wr( "$value = %s( $value );\n" % field.db_convert_func )
				src_type = field.db_convert_type
			
			if  field.ent_field_field != None:
				if src_type.name != field.ent_field_field.fieldType.name:
					self.wrt( "$$value = convert_${src_type}_to_${to_type}( $$value );\n", 
						{ 'src_type': src_type.name, 'to_type': field.ent_field_field.type.name } )
					
				# Nulls are always converted to null, no attempt is made to instantiate target object
				self.wrt( "$$value = $$value === null ? null : $class::with${key}( $$value );\n" ,
					{ 'class': field.ent_field.fieldType.phpClassName, 'key': field.ent_field_field.name })
			elif src_type.name != field.ent_field.fieldType.name:
				self.wrt( "$$value = convert_${src_type}_to_${to_type}( $$value );\n" ,
					{ 'src_type': src_type.name, 'to_type': field.ent_field.fieldType.name } )
			
			self.wr( "return $value;\n" )
			self.wr( "}\n" );
			
			#//// Member => DB
			self.wrt( "public static function _cnv_F${ent_field}_T${table}_${db_col}( $$value ) {\n" ,
				{ 'table': loc.table.name, 'db_col': field.db_field.name, 'ent_field': field.ent_field.name } )
			if field.db_convert_func == None:
				tar_type = field.db_field.fieldType
			else:
				tar_type = field.db_convert_type
			
			if  field.ent_field_field != None:
				# As above, if we have a null we simply produce null
				self.wr( "$value = $value === null ? null : $value->%s;\n" % field.ent_field_field.phpName )
				if tar_type.name != field.ent_field_field.fieldType.name:
					self.wrt( "$$value = convert_${from_type}_to_${to_type}( $$value );\n" ,
						{'from_type': field.ent_field_field.fieldType.name, 'to_type': tar_type.name } )
			elif tar_type.name != field.ent_field.fieldType.name:
				self.wrt( "$$value = convert_${from_type}_to_${to_type}( $$value );\n" ,
					{ 'from_type': field.ent_field.fieldType.name, 'to_type': tar_type.name } )
			
			if field.db_convert_func != None:
				self.wr( "$value = %s_inv( $value );\n" % field.db_convert_func );
			
			self.wr( "return $value;\n" )
			self.wr( "}\n\n" )
			
	
	##################################################################
	# Produces the loading functions
	def genMaybeLoad( self, en, loc ):
		self.wr( "//*** genMaybeLoad\n" )
		keys = en.getRecordKeyFields()
		self.wrt("""
//public only for helpers (so search can indicate item was loaded)
public function  _set_load_keys() {
	if( $$this->_load_keys !== null )	
		throw new Exception( "Not expecting a duplicate load / not supported" );
		
	$$this->_load_keys = array();
	$loadkeys
	
	//return true if keys are complete, false otherwise
	return count( $$this->_load_keys ) > 0;
}

protected function _maybeLoad() {
	$$this->_set_load_keys();
		
	if( count( $$this->_load_keys ) == 0 )
		throw new Exception( "No keys specified/set for loading" );
		
	if( !dbs_dbsource_load( 
		self::getDB(),
		$table,
		$$this, 
		$$this->_load_keys,
		$members
		) ) {
		$$this->_load_keys = null;	//reset these keys as we didn't actually load
		return false;
	}
		
	return true;
}
""", { 
			'loadkeys': self.getKeyBlock( keys, False, lambda key:
				"$this->_load_keys['%s'] = %s;" % ( key.phpName, key.phpLoadDescriptor(loc) ) ),
			'table': loc.provider.phpTableRef( loc.table ),
			'members': self.getFields( self.FOR_LOAD, loc.fields )
			} )
				

	def getPHPMapArrayStr( self, tuples ):
		buf = "array(\n"
		for t in tuples:
			buf += "\t'%s' => %s,\n" % t
		buf += ")\n"
		return buf
	
	def genAddSave( self, en, loc ):
		self.wr( "//*** genAddSave\n" )
		keys = en.getRecordKeyFields()
		self.wrt("""
	
protected function _save( $$adding ) {

	$$keys = array();
	$savekeys

	//use the same keys as loading to allow for modifying key fields
	if( $$this->_load_keys !== null )
		$$usekeys = $$this->_load_keys;
	else
		$$usekeys = $$keys;
	
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
	//now these are the keys which identify this object
	$$this->_load_keys = $$keys;
}""", {
		'savekeys': self.getKeyBlock( keys, True, lambda key:
				"$keys['%s'] = %s;" % ( key.phpName, key.phpLoadDescriptor(loc) ) ),
		'readonly': self.getCheckReadOnly( keys ),
		'table': loc.provider.phpTableRef( loc.table ),
		'members': self.getSaveMembers( loc.fields ),
		'insertField': self.getInsertFields( loc, en )
		} )
	
	def getInsertFields( self, loc, en ):
		for field in en.fields.itervalues():
			mapfield = loc.getDBFieldForEntityField( field )
			if mapfield.db_field.lastInsert:
				return "array( '%s' => %s )" % ( field.phpName, self.dbField( mapfield ) )
		
		return "null"
		
	def getCheckReadOnly( self, keys ):
		buf = ""
		for i in range( len( keys ) ):
			if not keys[i].loadOnly:
				continue
			buf += "\tif( $this->__isDirty('%s') )\n" % keys[i].phpName
			buf += "\t\tthrow new DBS_FieldException( '%s', DBS_FieldException::SAVE_LOAD_ONLY );\n" % keys[i].phpName
		return buf
		
	def getSaveMembers( self, fields ):
		mem = []
		for field in fields:
			if field.ent_field.loadOnly:	#//for safety just don't save such fields
				continue;
			mem.append( ( field.ent_field.phpName, self.dbField( field ) ) )
		return self.getPHPMapArrayStr( mem )
					
	def genSearch( self, en, loc ):
		self.wr( "//*** genSearch\n" )
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
		$fields,
		$$args	//pass all options to loader
		);
}
		""",{
			'args': self.args_or_array( ),
			'fields': self.getFields( self.FOR_SEARCH, loc.fields ),
			'table': loc.provider.phpTableRef( loc.table ),
			'class': en.phpInstClassName,
			})
			
	FOR_SEARCH = 1
	FOR_LOAD = 2
	
	def getFields( self, forWhat, fields ):
		mem = []
		for field in fields:
			mem.append( ( field.ent_field.phpName, self.dbField( field ) ) )
		return self.getPHPMapArrayStr( mem )
	
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
	$$query[] = DBS_Query::limit( 1 );	//a safety measure
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
		'deletekeys': self.getKeyBlock( [ field.ent_field for field in loc.fields ], False, lambda field:
			"\t\t$keys[] = DBS_Query::match( '%s', $this->%s );\n" % ( field.phpName, field.phpName ) )
		} )
		
	
	##################################################################
	# The Nothing constructors 
	def genEmpty( self, en, loc ):
		self.wr( "//*** genEmpty\n" )
		self.wrt("""
static public function &withNothing() {
	$$ret = new $class();
	return $$ret;
}

static public function &createWithNothing() {
	$$ret = new $class();
	$$ret->_status = DBS_EntityBase::STATUS_NEW;
	return $$ret;
}
		""", { 'class': en.phpInstClassName } )
		
	##################################################################
	# 
	def genEntityDataTypes( self, en ):
		self.wr( "//*** genEntityDataTypes\n" )
		##
		self.wr( "\nprotected $_data_names = array(\n" )
		for field in en.fields.itervalues():
			self.wrt(
"""'$name' => array( $nonbasetype, $basetype ),
			""", { 
				'name': field.phpName,
				'nonbasetype': 'null'  if field.fieldType.baseType() else "'%s'" % field.fieldType.name,
				'basetype': "'%s'" % field.fieldType.getRootType().name 
				} )
		self.wr( ');\n' )
		
		##
		self.wr( "\nprotected $_data_defaults = array(\n" )
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
		self.wr( "\nprotected $_data_aliases = array(\n" )
		for alias in en.aliases.iteritems():
			self.wrt("""	'$alias' => '$name',\n""", {
				'alias': self.memberName(alias[0]),
				'name': self.memberName(alias[1]) } )
		self.wr( ');\n' )
		
		##
		# Produce the checkType function. This produces a switch statement on
		# the field name and checks the type of the field in the case block.
		self.wr( """	
	protected function _checkType( $field, $value ) {
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
				if field.maxLen != None:
					self.wr( self._if(
						"strlen( $value ) > %d" % field.maxLen,
						self._throwSetFieldException( field, 'TYPE_LEN' )
						) )
						
			self.wr( "\tbreak;\n" );
		self.wr("""
		}
	}
		""")
	
	##################################################################
	# 
	def genOpenEntityClass( self, en ):
		self.wrt("""
class $class extends DBS_EntityBase {
	protected function __construct() {
		parent::__construct();
	} 
	
	static public function &_privConstruct() {
		$$item = new $inst();
		return $$item;
	}
"""	, {'class': en.phpClassName,
		'inst': en.phpInstClassName
		} )

	def genCloseEntityClass( self, en ):
		self.wrt( 
"""} //end of class

function &_${inst}_privConstruct() {
	return ${inst}::_privConstruct();
}

""", {	'inst': en.phpInstClassName	} )
		
		
		
	#/***************************************************************************
	#* Form Generation
	#***************************************************************************/	
	def genForm( self, form ):
		self.wrt("""<?php
		
	require_once dirname(__FILE__).'/schema.inc';
	require_once 'persephone/form_base.inc';
					
	class Form${class} extends DBS_FormBase_QuickForm {
	
		const ENTITY = '${entity}';
		
		private $$createFrom;
		
		protected function __construct( &$$form ) {
			parent::__construct($$form);
		}
		
		static public function &fromRequest() {
			$$ret =& self::_setup();
			$$ret->isNew = self::isNew();
			return $$ret;
		}
		
		//
		static public function &create( $$from = null ) {
			$$ret =& self::_setup();
			$$ret->createFrom = $$from;
			$$ret->isNew = $$from === null || $$from->isNew();
			return $$ret;
		}
		
		static private function &_setup( ) {
			$$form = new HTML_QuickForm( '${class}', 'POST', '', '', 
				array( 'class' => 'dbsform' ) );
		""", { 'class': form.phpClassName,
			'entity': form.entity.phpClassName,
			})

		for formfield in form.fields:
			field = form.entity.fields[formfield.name]
				
			if formfield.readonly:
				self.wr( "\t$form->addElement( 'static', '_ro_%s', %s );\n" % ( field.phpFormName, field.phpFormLabel ) )
					
			#//readonly also need to propagate their value, perhaps just for keys?
			if formfield.hidden or formfield.readonly:
				self.wr( "\t$form->addElement( 'hidden', '%s' );\n" % field.phpFormName );
			else:
				self.wr( "\t$form->addElement( '%s', '%s', %s, %s );\n" 
					% ( self.formTypeOf( field.fieldType ), field.phpFormName, field.phpFormLabel, self.formOptionsOf( field ) ) )
					
			if field.maxLen != None:
				self.wr( "\t$form->addRule( '%s', 	%s . ' may not be longer than %d characters.', 'maxlength', %d, 'client' );\n"
						% ( field.phpFormName, field.phpFormLabel, field.maxLen, field.maxLen )	)
							
			#	//TODO: isNumeric function, but where?
			if field.fieldType.name == 'Integer' or field.fieldType.name == 'Decimal' or field.fieldType.name == 'Float':
				self.wr( "\t$form->addRule( '%s', %s . ' must be numeric.', 'numeric', true, 'client' );\n" 
						% ( field.phpFormName, field.phpFormLabel )	)

		self.wrt("""
			$$ret = new Form${class}( $$form );
			return $$ret;
		}
		
		protected function addActions() {
			if( $$this->isNew )
				$$submit[] =& $$this->form->createElement( 'submit', DBS_FormBase_QuickForm::T_ACTION_ADD, 'Add' );
			else
				$$submit[] =& $$this->form->createElement( 'submit', DBS_FormBase_QuickForm::T_ACTION_SAVE, 'Save' );
			$delete
			$$this->form->addGroup( $$submit, DBS_FormBase_QuickForm::T_SUBMITROW );
		}
		
		public function inject( &$$entity, $$overrideRequest = false ) {
			$$values = array();
		""",{ 'class': form.phpClassName,
				'delete': '$submit[] =& $this->form->createElement( \'submit\', DBS_FormBase_QuickForm::T_ACTION_DELETE, \'Delete\' );' if form.allowDelete else '',
				 })
				
		for formfield in form.fields:
			field = form.entity.fields[formfield.name]
				
			#//only inject those values set on the object, this requires a forced load (TODO: what about lazy loading... perhaps only if status is not EXTANT )
			self.wr( "if( $entity->__has( '%s' ) ) {\n" % formfield.phpMemberName )
			self.wr( "$values['%s'] = %s;\n " % ( field.phpFormName, self.formInFunc( field, formfield ) ) )
			if formfield.readonly: #//set above in _setup
				self.wr( "$values['_ro_%s'] = %s;\n " % ( field.phpFormName, self.formInFunc( field, formfield )  ) )
				
			self.wr( "}\n" )
		
		self.wrt("""
			if( $$overrideRequest )
				$$this->form->setConstants( $$values );
			else
				$$this->form->setDefaults( $$values );
		}
	
		public function extractKeys( &$$entity ) {
			${extractKeys}
		}
		
		public function extract( &$$entity ) {
			${extract}
		}
	
		public function execute() {
			if( !$$this->hasAction() ) {
				if( $$this->createFrom !== null )
					$$this->inject( $$this->createFrom );
			}
				
			$$showForm = true;
			if( $$this->validate() ) {
				if( $$this->isNew ) {
					$$rule = ${class}::createWithNothing();
				} else {
					$$rule = ${class}::withNothing();
					$$this->extractKeys( $$rule );
					$$rule->find();
				}
				
				$$this->extract( $$rule );
				if( $$this->getAction() == DBS_FormBase::ACTION_SAVE ) {
					$$rule->save();
					$$this->inject( $$rule, true );	//capture any logic/new values from entity
					print( "<p class='success'>Saved.</p>" );
				} else if( $$this->getAction() == DBS_FormBase::ACTION_ADD ) {
					$$rule->add();
					$$this->isNew = false;
					$$this->inject( $$rule, true );	//capture any logic/new values from entity
					print( "<p class='success'>Added.</p>" );
				} else if( $$this->getAction() == DBS_FormBase::ACTION_DELETE ) {
					$$rule->delete();
					$$showForm = false;
					print( "<p class='success'>Deleted.</p>" );
				}
			}
			
			if( $$showForm ) {
				$$this->addActions();
				echo $$this->toHTML();
			}
		}
	
	}
?>""", { 'class': form.entity.phpClassName,
	'extractKeys': self.formExtract( form, True ),
	'extract': self.formExtract( form, False ),
	 } )
	
	
	def formExtract( self, form, keys ):
		buf = ""
		for formfield in form.fields:
			field = form.entity.fields[formfield.name]
			
			#//skip keys in key mode, or only keys otherwise
			if (field.keyType != DBSchema.KEY_TYPE_NONE) != keys:
				continue;
				
			#//TODO: what does readonly mean here...? (Standard form always expects to load keys, even read only ones...)
			#if formfield.readonly:
			#	continue;
				
			#//TODO: references for entitites
			buf += "$raw = $this->form->exportValue('%s');\n" % field.phpFormName
			buf += self.formOutFunc( field, formfield )
		return buf
		
		
	def formLinkFieldOf( self, ent ):
		keys = ent.getRecordKeyFields()
		if len( keys ) != 1:
			raise Exception, "Type %s has too many keys" % ent.name
		return keys[0]			
	
	
	def formTypeOf( self, atype ):
		atype = atype.getRootType()
		if isinstance( atype, DBSchema.Entity ):
			link = self.formLinkFieldOf( atype )
			if atype.getTitle() != None:
				return 'select'
			atype = link.fieldType;
		
		if atype.name in ['String','Integer','Decimal', 'Float','DateTime','Date','Time']:
		 	return 'text'
		if atype.name == 'Text':
			return 'textarea';
		if atype.name == 'Bool':
			return 'select';
		
		raise Exception, "Unsupported Form type: %s " % atype.name
	
	
	def formNameOf( self, ent ):
		return "_dbs_%s" % ent.name #//TODO: proper/safe naming
	
	
	def formLabelOf( self, form_field ):
		return '\'' + xml( form_field.label ) + '\''	#//TODO:FEATURE: some label lookup/replacement
	
	##
	# Creates the PHP fragment for the HTMLQuickForm options for the field.
	def formOptionsOf( self, ent ):
		if ent.fieldType.getRootType().name == 'Bool':
			return "array( 0 => 'False', 1 => 'True' )"
			
		# linked entities load the keys/names of all the possible items and present it as a select box
		if isinstance( ent.fieldType, DBSchema.Entity ):
			link = self.formLinkFieldOf( ent.fieldType )
			title = ent.fieldType.getTitle()
			if title != None:
				#//just match all records by default
				return " _dbs_form_loadentityselect( %s::search( DBS_Query::matchAll() ), '%s','%s' )" \
					% ( ent.fieldType.phpClassName, self.memberName( link.name ), self.memberName( title.name ) )
		
		if ent.fieldType.name in [ 'String', 'Text' ] and ent.maxLen != None:
			return "array( 'maxlength' => %d ) " % ent.maxLen
			
		return 'array()'
	
	##
	# Creates the PHP fragment to take a value from the entity and prepare it for
	# for form.
	# TODO: Handle nulls in sub field references
	def formInFunc( self, ent, ff ):
		if isinstance( ent.fieldType, DBSchema.Entity ):
			link = self.formLinkFieldOf( ent.fieldType )
			atype = link.fieldType
			sub = '->' + self.memberName( link.name )
		else:
			atype = ent.fieldType.getRootType()
			sub = ''
				
		return "_dbs_formin_%s( $entity->%s%s )"	% ( atype.name, ff.phpMemberName, sub )
	
	
	##
	# Creates the PHP fragment to take a value from the form and convert it to
	# the entity field type.
	def formOutFunc( self, ent, ff ):
		# when referencing objects we'll use the lazy loading "withNothing"
		if isinstance( ent.fieldType, DBSchema.Entity ):
			link = self.formLinkFieldOf( ent.fieldType )
			atype = link.fieldType
			sub = 'unset($ent); $ent =& ' + ent.fieldType.phpClassName + "::withNothing();\n"
			sub += "$ent->%s = $raw;\n" % self.memberName( link.name )
			assign = '= new DBS_Ref( $ent )'
		else:
			atype = ent.fieldType.getRootType()
			assign = '= $raw'
			sub = ''
		
		buf = "$raw = _dbs_formout_%s($raw);\n" % atype.name
		buf += sub
		buf += "$entity->%s %s;\n" % ( ff.phpMemberName, assign )
		return buf
	
	
		
	#/***************************************************************************
	#* Listing Generation
	#***************************************************************************/	
	def genListing( self, listing ):
		self.wrt("""<?php
		
	require_once dirname(__FILE__).'/schema.inc';
	require_once 'persephone/listing_base.inc';
					
	class Listing${class} extends DBS_ListingBase {
	
		protected $$entity = '${entity}';
	
		protected function __construct( $$searchArgs ) {
			parent::__construct( $$searchArgs );
		}
		
		static public function search( ) {
			$args
			return new Listing${class}( $$args );
		}""", { 'class': listing.phpClassName,
				'entity': listing.entity.phpClassName,
				'args': self.args_or_array()
			})
	
		self.wr( "protected $fields = array(\n" )
		for field in listing.fields:
			if  field.entField == None:
				membername = '@SELF'
			else:
				membername = self.memberName( field.entField.name )
			
			if field.convertFunc != None:
				converter = field.convertFunc
			else:
				#//TODO: support fallback through base type chain for custom types
				converter = "format_listing_%s" % field.entField.fieldType.name
			
			self.wr( "\tarray( '%s', '%s', '%s'),\n" % ( membername, self.addslashes(field.label), converter ) )
				
		self.wr( ");\n" )
		self.wr( "}\n" )
		
		
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
	# @param fields [in] the fields to consider for keys
	# @param checkAdding [in] allow that LOAD_ONLY fields to be absent if "$adding" is true
	# @param statement [in] assignment statement for each key
	def getKeyBlock( self, fields, checkAdding, statement ):
		buf = "";
		#only need one ALT_RECORD_KEY, but need all RECORD_KEY
		for key in fields:
			if key.keyType == DBSchema.KEY_TYPE_NONE:
				continue;
				
			if key.keyType == DBSchema.KEY_TYPE_RECORD:
				_else = self._throwFieldException( key, "MISSING_REQ" )
				if checkAdding and key.loadOnly:	#TODO: check LAST_INSERT_ID, but see comment in test schema first!
					_else = self._if( '!$adding',	_else )
				buf += self._if(
					self._this_has( key ),
					statement( key ),
					_else
					)
			elif key.keyType == DBSchema.KEY_TYPE_ALT:
				buf += self._if(
					self._this_has( key ),
					statement( key )
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
	def constantExpr( self, fieldType, value ):
		tname = fieldType.name
		if tname == 'String' or tname =='Text':
			return "'%s'" % self.addslashes( value )
		elif tname == 'Integer':
			return "%d" % atol( value )
		elif tname == 'Float' or tname == 'Decimal':
			return "%f" % atof( value )
		else:
			raise Error, "Unknown type for constant %s " % tname
		
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
		
		#all caps  Ex: UPPER => upper
		#PYTHON: if re.match( '(?u)^\P{Lu}+$', str ):
		if re.search('(?u)^[A-Z]+$', str ):
			return str.lower()
		
		#one leading cap  Ex: BasicName => basicName
		#PYTHON: ^(\p{Lu})([^\p{Lu}].*)$
		m = re.search( '^([A-Z])([^A-Z].*)$', str )
		if m:
			return m.group(1).lower() + m.group(2)
			
		#many leading caps Ex: IDString => idString
		#PYTHON: ^(\p{Lu}+)(\p{Lu}[^\p{Lu}])
		m = re.search( '^([A-Z]+)([A-Z][^A-Z].*)$', str )
		if not m:
			raise Error, "Unconvertable member: %s " % str
		return m.group(1).lower() + m.group(2)

	def dbField( self, field ):
		return "array( '%s', '%s' )" % (field.db_field.name, field.db_field.fieldType.name)
	
	def args_or_array( self ):
		#//allow an array to be used instead of variable arguments
		return '$args = func_get_args();	\
			if( count( $args ) === 1 && is_array( $args[0] ) )\
				$args = $args[0];\
			'

	# End of PHP Language Constructs
	##################################################################
	