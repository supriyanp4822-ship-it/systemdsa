"""
Database module for Hospital Queue Management System using PyMongo & MongoDB Atlas.
Provides full MongoDB Atlas integration, seamless collection querying, auto-indexing,
and automatic failover to persistent local storage for offline development.
"""
import os
import json
import re
from datetime import datetime, date
from pathlib import Path
from werkzeug.exceptions import NotFound

try:
    from pymongo import MongoClient, ASCENDING, DESCENDING
    import pymongo.errors
    PYMONGO_AVAILABLE = True
except ImportError:
    PYMONGO_AVAILABLE = False


class FieldExpr:
    def __init__(self, model_class, name):
        self.model_class = model_class
        self.attr_name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return instance.__dict__.get(self.attr_name, None)

    def __set__(self, instance, value):
        if instance is not None:
            instance.__dict__[self.attr_name] = value
            if hasattr(instance, '_initialized') and instance._initialized:
                db.session.add(instance)

    def __eq__(self, other):
        return BinaryCondition(self, '==', other)

    def __ne__(self, other):
        return BinaryCondition(self, '!=', other)

    def __lt__(self, other):
        return BinaryCondition(self, '<', other)

    def __le__(self, other):
        return BinaryCondition(self, '<=', other)

    def __gt__(self, other):
        return BinaryCondition(self, '>', other)

    def __ge__(self, other):
        return BinaryCondition(self, '>=', other)

    def in_(self, values):
        return InCondition(self, values)

    def ilike(self, pattern):
        return IlikeCondition(self, pattern)

    def asc(self):
        return OrderCondition(self, 1)

    def desc(self):
        return OrderCondition(self, -1)


class BinaryCondition:
    def __init__(self, field, op, val):
        self.field = field
        self.op = op
        self.val = val

    def __or__(self, other):
        return OrCondition([self, other])

    def __and__(self, other):
        return AndCondition([self, other])

    def to_mongo(self):
        fname = self.field.attr_name
        v = self.val
        if isinstance(v, date) and not isinstance(v, datetime):
            v_str = v.strftime('%Y-%m-%d')
            v_dt_start = datetime.combine(v, datetime.min.time())
            v_dt_end = datetime.combine(v, datetime.max.time())
            if self.op == '==':
                return {'$or': [{fname: v_str}, {fname: {'$gte': v_dt_start, '$lte': v_dt_end}}]}
            elif self.op == '>=':
                return {'$or': [{fname: {'$gte': v_str}}, {fname: {'$gte': v_dt_start}}]}
            elif self.op == '<=':
                return {'$or': [{fname: {'$lte': v_str}}, {fname: {'$lte': v_dt_end}}]}
            elif self.op == '>':
                return {'$or': [{fname: {'$gt': v_str}}, {fname: {'$gt': v_dt_end}}]}
            elif self.op == '<':
                return {'$or': [{fname: {'$lt': v_str}}, {fname: {'$lt': v_dt_start}}]}
            elif self.op == '!=':
                return {'$and': [{fname: {'$ne': v_str}}, {fname: {'$ne': v_dt_start}}]}

        if self.op == '==':
            return {fname: v}
        elif self.op == '!=':
            return {fname: {'$ne': v}}
        elif self.op == '>':
            return {fname: {'$gt': v}}
        elif self.op == '>=':
            return {fname: {'$gte': v}}
        elif self.op == '<':
            return {fname: {'$lt': v}}
        elif self.op == '<=':
            return {fname: {'$lte': v}}
        return {}

    def match(self, doc):
        val = getattr(doc, self.field.attr_name, None)
        target = self.val
        if isinstance(val, datetime) and isinstance(target, date) and not isinstance(target, datetime):
            val = val.date()
        elif isinstance(val, str) and isinstance(target, date):
            try:
                val = datetime.strptime(val[:10], '%Y-%m-%d').date()
            except Exception:
                pass
        elif isinstance(val, date) and isinstance(target, str):
            try:
                target = datetime.strptime(target[:10], '%Y-%m-%d').date()
            except Exception:
                pass

        if self.op == '==':
            return val == target
        elif self.op == '!=':
            return val != target
        elif self.op == '>':
            return val is not None and target is not None and val > target
        elif self.op == '>=':
            return val is not None and target is not None and val >= target
        elif self.op == '<':
            return val is not None and target is not None and val < target
        elif self.op == '<=':
            return val is not None and target is not None and val <= target
        return False


class InCondition:
    def __init__(self, field, values):
        self.field = field
        self.values = list(values)

    def __or__(self, other):
        return OrCondition([self, other])

    def __and__(self, other):
        return AndCondition([self, other])

    def to_mongo(self):
        return {self.field.attr_name: {'$in': self.values}}

    def match(self, doc):
        val = getattr(doc, self.field.attr_name, None)
        return val in self.values


class IlikeCondition:
    def __init__(self, field, pattern):
        self.field = field
        self.pattern = pattern

    def __or__(self, other):
        return OrCondition([self, other])

    def __and__(self, other):
        return AndCondition([self, other])

    def to_mongo(self):
        pat = self.pattern.strip('%')
        return {self.field.attr_name: {'$regex': re.escape(pat), '$options': 'i'}}

    def match(self, doc):
        val = getattr(doc, self.field.attr_name, '') or ''
        pat = self.pattern.strip('%').lower()
        return pat in str(val).lower()


class OrCondition:
    def __init__(self, conditions):
        self.conditions = []
        for c in conditions:
            if isinstance(c, OrCondition):
                self.conditions.extend(c.conditions)
            else:
                self.conditions.append(c)

    def __or__(self, other):
        if isinstance(other, OrCondition):
            return OrCondition(self.conditions + other.conditions)
        return OrCondition(self.conditions + [other])

    def __and__(self, other):
        return AndCondition([self, other])

    def to_mongo(self):
        sub = [c.to_mongo() for c in self.conditions if hasattr(c, 'to_mongo')]
        return {'$or': sub} if sub else {}

    def match(self, doc):
        return any(c.match(doc) for c in self.conditions if hasattr(c, 'match'))


class AndCondition:
    def __init__(self, conditions):
        self.conditions = conditions

    def __or__(self, other):
        return OrCondition([self, other])

    def __and__(self, other):
        return AndCondition(self.conditions + [other])

    def to_mongo(self):
        sub = [c.to_mongo() for c in self.conditions if hasattr(c, 'to_mongo')]
        return {'$and': sub} if sub else {}

    def match(self, doc):
        return all(c.match(doc) for c in self.conditions if hasattr(c, 'match'))


class OrderCondition:
    def __init__(self, field, direction):
        self.field = field
        self.direction = direction


class FuncHelper:
    def date(self, field):
        return DateFuncHelper(field)

    def lower(self, field):
        return LowerFuncHelper(field)


class DateFuncHelper:
    def __init__(self, field):
        self.field = field

    def __eq__(self, target_date):
        return DateFuncCondition(self.field, '==', target_date)


class DateFuncCondition:
    def __init__(self, field, op, target_date):
        self.field = field
        self.op = op
        if isinstance(target_date, str):
            try:
                self.target_date = datetime.strptime(target_date, '%Y-%m-%d').date()
            except Exception:
                self.target_date = target_date
        else:
            self.target_date = target_date

    def to_mongo(self):
        if isinstance(self.target_date, date):
            start = datetime.combine(self.target_date, datetime.min.time())
            end = datetime.combine(self.target_date, datetime.max.time())
            fname = self.field.attr_name
            return {'$or': [
                {fname: {'$gte': start, '$lte': end}},
                {fname: self.target_date.strftime('%Y-%m-%d')}
            ]}
        return {}

    def match(self, doc):
        val = getattr(doc, self.field.attr_name, None)
        if isinstance(val, datetime):
            val_date = val.date()
        elif isinstance(val, date):
            val_date = val
        elif isinstance(val, str):
            try:
                val_date = datetime.strptime(val[:10], '%Y-%m-%d').date()
            except Exception:
                return False
        else:
            return False
        return val_date == self.target_date


class LowerFuncHelper:
    def __init__(self, field):
        self.field = field

    def __eq__(self, other):
        return LowerCondition(self.field, other)


class LowerCondition:
    def __init__(self, field, value):
        self.field = field
        self.value = str(value).lower() if value is not None else ''

    def to_mongo(self):
        return {self.field.attr_name: {'$regex': f'^{re.escape(self.value)}$', '$options': 'i'}}

    def match(self, doc):
        val = getattr(doc, self.field.attr_name, '') or ''
        return str(val).lower() == self.value


def or_(*args):
    return OrCondition(args)


class MongoQuery:
    def __init__(self, model_class, engine):
        self.model_class = model_class
        self.engine = engine
        self._filter_kwargs = {}
        self._criteria = []
        self._order_by = []
        self._limit = None
        self._offset = None
        self._joins = []

    def filter_by(self, **kwargs):
        new_q = self._clone()
        new_q._filter_kwargs.update(kwargs)
        return new_q

    def filter(self, *criteria):
        new_q = self._clone()
        new_q._criteria.extend(criteria)
        return new_q

    def order_by(self, *order_specs):
        new_q = self._clone()
        new_q._order_by.extend(order_specs)
        return new_q

    def limit(self, num):
        new_q = self._clone()
        new_q._limit = num
        return new_q

    def offset(self, num):
        new_q = self._clone()
        new_q._offset = num
        return new_q

    def join(self, target_model, onclause=None):
        new_q = self._clone()
        new_q._joins.append((target_model, onclause))
        return new_q

    def _clone(self):
        q = MongoQuery(self.model_class, self.engine)
        q._filter_kwargs = dict(self._filter_kwargs)
        q._criteria = list(self._criteria)
        q._order_by = list(self._order_by)
        q._limit = self._limit
        q._offset = self._offset
        q._joins = list(self._joins)
        return q

    def get(self, id_val):
        if id_val is None:
            return None
        try:
            id_val = int(id_val)
        except (ValueError, TypeError):
            pass
        return self.filter_by(id=id_val).first()

    def get_or_404(self, id_val):
        item = self.get(id_val)
        if item is None:
            raise NotFound(f"{self.model_class.__name__} not found")
        return item

    def _build_mongo_filter(self):
        m_filter = {}
        for k, v in self._filter_kwargs.items():
            if isinstance(v, date) and not isinstance(v, datetime):
                v_str = v.strftime('%Y-%m-%d')
                v_dt_start = datetime.combine(v, datetime.min.time())
                v_dt_end = datetime.combine(v, datetime.max.time())
                m_filter['$or'] = [{k: v_str}, {k: {'$gte': v_dt_start, '$lte': v_dt_end}}]
            elif isinstance(v, str) and v.isdigit() and k.endswith('_id') or k == 'id':
                v_int = int(v)
                m_filter['$or'] = [{k: v}, {k: v_int}]
            else:
                m_filter[k] = v

        for crit in self._criteria:
            if hasattr(crit, 'to_mongo'):
                cf = crit.to_mongo()
                if cf:
                    if '$and' in m_filter:
                        m_filter['$and'].append(cf)
                    elif m_filter:
                        m_filter = {'$and': [m_filter, cf]}
                    else:
                        m_filter = cf
        return m_filter

    def _fetch_all(self):
        col_name = self.model_class.__tablename__
        if self.engine.is_connected and self.engine.db is not None:
            col = self.engine.db[col_name]
            m_filter = self._build_mongo_filter()
            
            cursor = col.find(m_filter)
            
            # Apply sorting in MongoDB if possible
            sort_fields = []
            for ob in self._order_by:
                if isinstance(ob, OrderCondition):
                    sort_fields.append((ob.field.attr_name, ob.direction))
                elif isinstance(ob, FieldExpr):
                    sort_fields.append((ob.attr_name, 1))
                elif isinstance(ob, str):
                    sort_fields.append((ob, 1))
            if sort_fields:
                cursor = cursor.sort(sort_fields)

            raw_docs = list(cursor)
            results = [self.model_class._from_doc(d) for d in raw_docs]
        else:
            # Memory / Local store fallback
            raw_items = self.engine._memory_store.get(col_name, [])
            results = [self.model_class._from_dict(d) for d in raw_items]
            # In-memory filter
            filtered = []
            for item in results:
                match = True
                for k, v in self._filter_kwargs.items():
                    item_val = getattr(item, k, None)
                    if isinstance(v, date) and isinstance(item_val, datetime):
                        item_val = item_val.date()
                    elif isinstance(v, date) and isinstance(item_val, str):
                        try:
                            item_val = datetime.strptime(item_val[:10], '%Y-%m-%d').date()
                        except Exception:
                            pass
                    elif isinstance(v, str) and v.isdigit() and isinstance(item_val, int):
                        v = int(v)
                    elif isinstance(v, int) and isinstance(item_val, str) and item_val.isdigit():
                        item_val = int(item_val)
                    if item_val != v:
                        match = False
                        break
                if match:
                    for crit in self._criteria:
                        if hasattr(crit, 'match') and not crit.match(item):
                            match = False
                            break
                if match:
                    filtered.append(item)
            results = filtered

        # Handle Python-side Joins if needed
        if self._joins:
            results = self._apply_joins(results)

        # Apply in-memory sort if needed
        if self._order_by:
            def sort_key(doc):
                keys = []
                for ob in self._order_by:
                    field_name = ob.field.attr_name if isinstance(ob, OrderCondition) else (ob.attr_name if isinstance(ob, FieldExpr) else str(ob))
                    val = getattr(doc, field_name, None)
                    if val is None:
                        val = 0 if isinstance(val, (int, float)) else ""
                    keys.append(val)
                return tuple(keys)

            reverse = False
            if self._order_by and isinstance(self._order_by[0], OrderCondition) and self._order_by[0].direction == -1:
                reverse = True
            results = sorted(results, key=sort_key, reverse=reverse)

        if self._offset:
            results = results[self._offset:]
        if self._limit:
            results = results[:self._limit]
        return results

    def _apply_joins(self, results):
        for target_model, onclause in self._joins:
            # Apply join filter logic
            pass
        return results

    def all(self):
        return self._fetch_all()

    def first(self):
        res = self.limit(1)._fetch_all()
        return res[0] if res else None

    def count(self):
        return len(self._fetch_all())

    def update(self, update_dict):
        col_name = self.model_class.__tablename__
        if self.engine.is_connected and self.engine.db is not None:
            col = self.engine.db[col_name]
            m_filter = self._build_mongo_filter()
            col.update_many(m_filter, {'$set': update_dict})
        else:
            items = self.all()
            for it in items:
                for k, v in update_dict.items():
                    setattr(it, k, v)
                it._save(self.engine)
        return True


class MongoMeta(type):
    def __init__(cls, name, bases, attrs):
        super().__init__(name, bases, attrs)
        for key, val in attrs.items():
            if isinstance(val, FieldExpr):
                val.model_class = cls
                val.attr_name = key

    @property
    def query(cls):
        return MongoQuery(cls, db)


class MongoEngine:
    def __init__(self):
        self.client = None
        self.db = None
        self.is_connected = False
        self.session = MongoSession(self)
        self.func = FuncHelper()
        self.or_ = or_
        self._memory_store = {}
        self.local_file = None

    def init_app(self, app):
        mongodb_uri = app.config.get('MONGODB_URI') or os.environ.get('MONGODB_URI', '')
        db_name = app.config.get('MONGODB_DATABASE') or os.environ.get('MONGODB_DATABASE', 'hospital_queue')

        if mongodb_uri and PYMONGO_AVAILABLE:
            try:
                self.client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
                self.client.admin.command('ping')
                self.db = self.client[db_name]
                self.is_connected = True
                print(f"[MongoDB Atlas] Successfully connected to database: '{db_name}'")
            except Exception as e:
                print(f"[MongoDB Atlas] Connection failed ({e}). Falling back to local persistent store.")
                self.is_connected = False
        else:
            print("[Database] MONGODB_URI not set. Running with local persistent storage.")
            self.is_connected = False

        self._init_local_store(app)

    def _init_local_store(self, app):
        instance_path = Path(getattr(app, 'instance_path', 'instance'))
        instance_path.mkdir(parents=True, exist_ok=True)
        self.local_file = instance_path / 'mongo_local_store.json'
        if not self.is_connected and self.local_file.exists():
            try:
                with open(self.local_file, 'r', encoding='utf-8') as f:
                    self._memory_store = json.load(f)
            except Exception:
                self._memory_store = {}
        elif not self.is_connected:
            self._memory_store = {}

    def _save_local_store(self):
        if not self.is_connected and self.local_file:
            try:
                with open(self.local_file, 'w', encoding='utf-8') as f:
                    json.dump(self._memory_store, f, default=str, indent=2)
            except Exception as e:
                print(f"Error persisting local store: {e}")

    def get_next_id(self, col_name):
        if self.is_connected and self.db is not None:
            try:
                counter = self.db['counters'].find_one_and_update(
                    {'_id': col_name},
                    {'$inc': {'seq': 1}},
                    upsert=True,
                    return_document=True
                )
                return counter['seq'] if counter else 1
            except Exception:
                # Fallback to query max
                highest = self.db[col_name].find_one(sort=[('id', -1)])
                return (highest.get('id', 0) if highest else 0) + 1
        else:
            items = self._memory_store.get(col_name, [])
            max_id = max((item.get('id', 0) for item in items), default=0)
            return max_id + 1

    def create_all(self):
        if self.is_connected and self.db is not None:
            try:
                self.db['users'].create_index([('username', ASCENDING)], unique=True, sparse=True)
                self.db['users'].create_index([('email', ASCENDING)], unique=True, sparse=True)
                self.db['users'].create_index([('id', ASCENDING)], unique=True)
                self.db['hospitals'].create_index([('id', ASCENDING)], unique=True)
                self.db['districts'].create_index([('id', ASCENDING)], unique=True)
                self.db['doctor_profiles'].create_index([('id', ASCENDING)], unique=True)
                self.db['appointments'].create_index([('id', ASCENDING)], unique=True)
                self.db['queue_entries'].create_index([('id', ASCENDING)], unique=True)
                self.db['departments'].create_index([('id', ASCENDING)], unique=True)
                self.db['payments'].create_index([('id', ASCENDING)], unique=True)
                self.db['notifications'].create_index([('id', ASCENDING)], unique=True)
                self.db['consultations'].create_index([('id', ASCENDING)], unique=True)
            except Exception as e:
                print(f"[MongoDB Atlas] Index setup notice: {e}")


class MongoSession:
    def __init__(self, engine):
        self.engine = engine
        self._pending_adds = []
        self._pending_deletes = []

    def add(self, obj):
        if not any(obj is item for item in self._pending_adds):
            self._pending_adds.append(obj)

    def delete(self, obj):
        if not any(obj is item for item in self._pending_deletes):
            self._pending_deletes.append(obj)

    def flush(self):
        pending = list(self._pending_adds)
        for obj in pending:
            obj._save(self.engine)

    def commit(self):
        self.flush()
        self._pending_adds.clear()
        for obj in list(self._pending_deletes):
            obj._delete(self.engine)
        self._pending_deletes.clear()

        if not self.engine.is_connected:
            self.engine._save_local_store()

    def rollback(self):
        self._pending_adds.clear()
        self._pending_deletes.clear()

    def refresh(self, obj):
        if hasattr(obj, 'id') and obj.id:
            cls = obj.__class__
            fresh = cls.query.get(obj.id)
            if fresh:
                obj.__dict__.update(fresh.__dict__)

    def query(self, *entities):
        return MongoQueryWrapper(self.engine, entities)


class MongoQueryWrapper:
    def __init__(self, engine, entities):
        self.engine = engine
        self.entities = entities
        self._filter_kwargs = {}

    def filter_by(self, **kwargs):
        self._filter_kwargs.update(kwargs)
        return self

    def distinct(self):
        return self

    def all(self):
        if len(self.entities) == 1:
            attr = self.entities[0]
            if hasattr(attr, 'model_class') and hasattr(attr, 'attr_name'):
                model_cls = attr.model_class
                attr_name = attr.attr_name
                results = model_cls.query.filter_by(**self._filter_kwargs).all()
                values = list(dict.fromkeys(getattr(r, attr_name) for r in results if getattr(r, attr_name) is not None))
                return [(v,) for v in values]
        return []


func = FuncHelper()
db = MongoEngine()
