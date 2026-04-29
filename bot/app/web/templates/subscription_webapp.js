(function() {
	//#region node_modules/svelte/src/internal/shared/utils.js
	var is_array = Array.isArray;
	var index_of = Array.prototype.indexOf;
	var includes = Array.prototype.includes;
	var array_from = Array.from;
	var define_property = Object.defineProperty;
	var get_descriptor = Object.getOwnPropertyDescriptor;
	var get_descriptors = Object.getOwnPropertyDescriptors;
	var object_prototype = Object.prototype;
	var array_prototype = Array.prototype;
	var get_prototype_of = Object.getPrototypeOf;
	var is_extensible = Object.isExtensible;
	/**
	* @param {any} thing
	* @returns {thing is Function}
	*/
	function is_function(thing) {
		return typeof thing === "function";
	}
	var noop = () => {};
	/** @param {Function} fn */
	function run(fn) {
		return fn();
	}
	/** @param {Array<() => void>} arr */
	function run_all(arr) {
		for (var i = 0; i < arr.length; i++) arr[i]();
	}
	/**
	* TODO replace with Promise.withResolvers once supported widely enough
	* @template [T=void]
	*/
	function deferred() {
		/** @type {(value: T) => void} */
		var resolve;
		/** @type {(reason: any) => void} */
		var reject;
		return {
			promise: new Promise((res, rej) => {
				resolve = res;
				reject = rej;
			}),
			resolve,
			reject
		};
	}
	/**
	* When encountering a situation like `let [a, b, c] = $derived(blah())`,
	* we need to stash an intermediate value that `a`, `b`, and `c` derive
	* from, in case it's an iterable
	* @template T
	* @param {ArrayLike<T> | Iterable<T>} value
	* @param {number} [n]
	* @returns {Array<T>}
	*/
	function to_array(value, n) {
		if (Array.isArray(value)) return value;
		if (n === void 0 || !(Symbol.iterator in value)) return Array.from(value);
		/** @type {T[]} */
		const array = [];
		for (const element of value) {
			array.push(element);
			if (array.length === n) break;
		}
		return array;
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/constants.js
	/**
	* An effect that does not destroy its child effects when it reruns.
	* Runs as part of render effects, i.e. not eagerly as part of tree traversal or effect flushing.
	*/
	var MANAGED_EFFECT = 1 << 24;
	var CLEAN = 1024;
	var DIRTY = 2048;
	var MAYBE_DIRTY = 4096;
	var INERT = 8192;
	var DESTROYED = 16384;
	/** Set once a reaction has run for the first time */
	var REACTION_RAN = 32768;
	/** Effect is in the process of getting destroyed. Can be observed in child teardown functions */
	var DESTROYING = 1 << 25;
	/**
	* 'Transparent' effects do not create a transition boundary.
	* This is on a block effect 99% of the time but may also be on a branch effect if its parent block effect was pruned
	*/
	var EFFECT_TRANSPARENT = 65536;
	var HEAD_EFFECT = 1 << 18;
	var EFFECT_PRESERVED = 1 << 19;
	var USER_EFFECT = 1 << 20;
	var EFFECT_OFFSCREEN = 1 << 25;
	/**
	* Tells that we marked this derived and its reactions as visited during the "mark as (maybe) dirty"-phase.
	* Will be lifted during execution of the derived and during checking its dirty state (both are necessary
	* because a derived might be checked but not executed). This is a pure performance optimization flag and
	* should not be used for any other purpose!
	*/
	var WAS_MARKED = 65536;
	var REACTION_IS_UPDATING = 1 << 21;
	var ASYNC = 1 << 22;
	var ERROR_VALUE = 1 << 23;
	var STATE_SYMBOL = Symbol("$state");
	var LEGACY_PROPS = Symbol("legacy props");
	var LOADING_ATTR_SYMBOL = Symbol("");
	/** allow users to ignore aborted signal errors if `reason.name === 'StaleReactionError` */
	var STALE_REACTION = new class StaleReactionError extends Error {
		name = "StaleReactionError";
		message = "The reaction that called `getAbortSignal()` was re-run or destroyed";
	}();
	var IS_XHTML = !!globalThis.document?.contentType && /* @__PURE__ */ globalThis.document.contentType.includes("xml");
	/**
	* `%name%(...)` can only be used during component initialisation
	* @param {string} name
	* @returns {never}
	*/
	function lifecycle_outside_component(name) {
		throw new Error(`https://svelte.dev/e/lifecycle_outside_component`);
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/errors.js
	/**
	* Cannot create a `$derived(...)` with an `await` expression outside of an effect tree
	* @returns {never}
	*/
	function async_derived_orphan() {
		throw new Error(`https://svelte.dev/e/async_derived_orphan`);
	}
	/**
	* Keyed each block has duplicate key `%value%` at indexes %a% and %b%
	* @param {string} a
	* @param {string} b
	* @param {string | undefined | null} [value]
	* @returns {never}
	*/
	function each_key_duplicate(a, b, value) {
		throw new Error(`https://svelte.dev/e/each_key_duplicate`);
	}
	/**
	* `%rune%` cannot be used inside an effect cleanup function
	* @param {string} rune
	* @returns {never}
	*/
	function effect_in_teardown(rune) {
		throw new Error(`https://svelte.dev/e/effect_in_teardown`);
	}
	/**
	* Effect cannot be created inside a `$derived` value that was not itself created inside an effect
	* @returns {never}
	*/
	function effect_in_unowned_derived() {
		throw new Error(`https://svelte.dev/e/effect_in_unowned_derived`);
	}
	/**
	* `%rune%` can only be used inside an effect (e.g. during component initialisation)
	* @param {string} rune
	* @returns {never}
	*/
	function effect_orphan(rune) {
		throw new Error(`https://svelte.dev/e/effect_orphan`);
	}
	/**
	* Maximum update depth exceeded. This typically indicates that an effect reads and writes the same piece of state
	* @returns {never}
	*/
	function effect_update_depth_exceeded() {
		throw new Error(`https://svelte.dev/e/effect_update_depth_exceeded`);
	}
	/**
	* Cannot do `bind:%key%={undefined}` when `%key%` has a fallback value
	* @param {string} key
	* @returns {never}
	*/
	function props_invalid_value(key) {
		throw new Error(`https://svelte.dev/e/props_invalid_value`);
	}
	/**
	* Property descriptors defined on `$state` objects must contain `value` and always be `enumerable`, `configurable` and `writable`.
	* @returns {never}
	*/
	function state_descriptors_fixed() {
		throw new Error(`https://svelte.dev/e/state_descriptors_fixed`);
	}
	/**
	* Cannot set prototype of `$state` object
	* @returns {never}
	*/
	function state_prototype_fixed() {
		throw new Error(`https://svelte.dev/e/state_prototype_fixed`);
	}
	/**
	* Updating state inside `$derived(...)`, `$inspect(...)` or a template expression is forbidden. If the value should not be reactive, declare it without `$state`
	* @returns {never}
	*/
	function state_unsafe_mutation() {
		throw new Error(`https://svelte.dev/e/state_unsafe_mutation`);
	}
	/**
	* A `<svelte:boundary>` `reset` function cannot be called while an error is still being handled
	* @returns {never}
	*/
	function svelte_boundary_reset_onerror() {
		throw new Error(`https://svelte.dev/e/svelte_boundary_reset_onerror`);
	}
	//#endregion
	//#region node_modules/svelte/src/constants.js
	var HYDRATION_ERROR = {};
	var UNINITIALIZED = Symbol();
	var NAMESPACE_HTML = "http://www.w3.org/1999/xhtml";
	var NAMESPACE_SVG = "http://www.w3.org/2000/svg";
	/**
	* Reading a derived belonging to a now-destroyed effect may result in stale values
	*/
	function derived_inert() {
		console.warn(`https://svelte.dev/e/derived_inert`);
	}
	/**
	* Hydration failed because the initial UI does not match what was rendered on the server. The error occurred near %location%
	* @param {string | undefined | null} [location]
	*/
	function hydration_mismatch(location) {
		console.warn(`https://svelte.dev/e/hydration_mismatch`);
	}
	/**
	* The `value` property of a `<select multiple>` element should be an array, but it received a non-array value. The selection will be kept as is.
	*/
	function select_multiple_invalid_value() {
		console.warn(`https://svelte.dev/e/select_multiple_invalid_value`);
	}
	/**
	* A `<svelte:boundary>` `reset` function only resets the boundary the first time it is called
	*/
	function svelte_boundary_reset_noop() {
		console.warn(`https://svelte.dev/e/svelte_boundary_reset_noop`);
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/dom/hydration.js
	/** @import { TemplateNode } from '#client' */
	/**
	* Use this variable to guard everything related to hydration code so it can be treeshaken out
	* if the user doesn't use the `hydrate` method and these code paths are therefore not needed.
	*/
	var hydrating = false;
	/** @param {boolean} value */
	function set_hydrating(value) {
		hydrating = value;
	}
	/**
	* The node that is currently being hydrated. This starts out as the first node inside the opening
	* <!--[--> comment, and updates each time a component calls `$.child(...)` or `$.sibling(...)`.
	* When entering a block (e.g. `{#if ...}`), `hydrate_node` is the block opening comment; by the
	* time we leave the block it is the closing comment, which serves as the block's anchor.
	* @type {TemplateNode}
	*/
	var hydrate_node;
	/** @param {TemplateNode | null} node */
	function set_hydrate_node(node) {
		if (node === null) {
			hydration_mismatch();
			throw HYDRATION_ERROR;
		}
		return hydrate_node = node;
	}
	function hydrate_next() {
		return set_hydrate_node(/* @__PURE__ */ get_next_sibling(hydrate_node));
	}
	/** @param {TemplateNode} node */
	function reset(node) {
		if (!hydrating) return;
		if (/* @__PURE__ */ get_next_sibling(hydrate_node) !== null) {
			hydration_mismatch();
			throw HYDRATION_ERROR;
		}
		hydrate_node = node;
	}
	function next(count = 1) {
		if (hydrating) {
			var i = count;
			var node = hydrate_node;
			while (i--) node = /* @__PURE__ */ get_next_sibling(node);
			hydrate_node = node;
		}
	}
	/**
	* Skips or removes (depending on {@link remove}) all nodes starting at `hydrate_node` up until the next hydration end comment
	* @param {boolean} remove
	*/
	function skip_nodes(remove = true) {
		var depth = 0;
		var node = hydrate_node;
		while (true) {
			if (node.nodeType === 8) {
				var data = node.data;
				if (data === "]") {
					if (depth === 0) return node;
					depth -= 1;
				} else if (data === "[" || data === "[!" || data[0] === "[" && !isNaN(Number(data.slice(1)))) depth += 1;
			}
			var next = /* @__PURE__ */ get_next_sibling(node);
			if (remove) node.remove();
			node = next;
		}
	}
	/**
	*
	* @param {TemplateNode} node
	*/
	function read_hydration_instruction(node) {
		if (!node || node.nodeType !== 8) {
			hydration_mismatch();
			throw HYDRATION_ERROR;
		}
		return node.data;
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/reactivity/equality.js
	/** @import { Equals } from '#client' */
	/** @type {Equals} */
	function equals(value) {
		return value === this.v;
	}
	/**
	* @param {unknown} a
	* @param {unknown} b
	* @returns {boolean}
	*/
	function safe_not_equal(a, b) {
		return a != a ? b == b : a !== b || a !== null && typeof a === "object" || typeof a === "function";
	}
	/** @type {Equals} */
	function safe_equals(value) {
		return !safe_not_equal(value, this.v);
	}
	//#endregion
	//#region node_modules/svelte/src/internal/flags/index.js
	/** True if experimental.async=true */
	var async_mode_flag = false;
	/** True if we're not certain that we only have Svelte 5 code in the compilation */
	var legacy_mode_flag = false;
	function enable_legacy_mode_flag() {
		legacy_mode_flag = true;
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/context.js
	/** @import { ComponentContext, DevStackEntry, Effect } from '#client' */
	/** @type {ComponentContext | null} */
	var component_context = null;
	/** @param {ComponentContext | null} context */
	function set_component_context(context) {
		component_context = context;
	}
	/**
	* @param {Record<string, unknown>} props
	* @param {any} runes
	* @param {Function} [fn]
	* @returns {void}
	*/
	function push(props, runes = false, fn) {
		component_context = {
			p: component_context,
			i: false,
			c: null,
			e: null,
			s: props,
			x: null,
			r: active_effect,
			l: legacy_mode_flag && !runes ? {
				s: null,
				u: null,
				$: []
			} : null
		};
	}
	/**
	* @template {Record<string, any>} T
	* @param {T} [component]
	* @returns {T}
	*/
	function pop(component) {
		var context = component_context;
		var effects = context.e;
		if (effects !== null) {
			context.e = null;
			for (var fn of effects) create_user_effect(fn);
		}
		if (component !== void 0) context.x = component;
		context.i = true;
		component_context = context.p;
		return component ?? {};
	}
	/** @returns {boolean} */
	function is_runes() {
		return !legacy_mode_flag || component_context !== null && component_context.l === null;
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/dom/task.js
	/** @type {Array<() => void>} */
	var micro_tasks = [];
	function run_micro_tasks() {
		var tasks = micro_tasks;
		micro_tasks = [];
		run_all(tasks);
	}
	/**
	* @param {() => void} fn
	*/
	function queue_micro_task(fn) {
		if (micro_tasks.length === 0 && !is_flushing_sync) {
			var tasks = micro_tasks;
			queueMicrotask(() => {
				if (tasks === micro_tasks) run_micro_tasks();
			});
		}
		micro_tasks.push(fn);
	}
	/**
	* Synchronously run any queued tasks.
	*/
	function flush_tasks() {
		while (micro_tasks.length > 0) run_micro_tasks();
	}
	/**
	* @param {unknown} error
	*/
	function handle_error(error) {
		var effect = active_effect;
		if (effect === null) {
			/** @type {Derived} */ active_reaction.f |= ERROR_VALUE;
			return error;
		}
		if ((effect.f & 32768) === 0 && (effect.f & 4) === 0) throw error;
		invoke_error_boundary(error, effect);
	}
	/**
	* @param {unknown} error
	* @param {Effect | null} effect
	*/
	function invoke_error_boundary(error, effect) {
		while (effect !== null) {
			if ((effect.f & 128) !== 0) {
				if ((effect.f & 32768) === 0) throw error;
				try {
					/** @type {Boundary} */ effect.b.error(error);
					return;
				} catch (e) {
					error = e;
				}
			}
			effect = effect.parent;
		}
		throw error;
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/reactivity/status.js
	/** @import { Derived, Signal } from '#client' */
	var STATUS_MASK = ~(DIRTY | MAYBE_DIRTY | CLEAN);
	/**
	* @param {Signal} signal
	* @param {number} status
	*/
	function set_signal_status(signal, status) {
		signal.f = signal.f & STATUS_MASK | status;
	}
	/**
	* Set a derived's status to CLEAN or MAYBE_DIRTY based on its connection state.
	* @param {Derived} derived
	*/
	function update_derived_status(derived) {
		if ((derived.f & 512) !== 0 || derived.deps === null) set_signal_status(derived, CLEAN);
		else set_signal_status(derived, MAYBE_DIRTY);
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/reactivity/utils.js
	/** @import { Derived, Effect, Value } from '#client' */
	/**
	* @param {Value[] | null} deps
	*/
	function clear_marked(deps) {
		if (deps === null) return;
		for (const dep of deps) {
			if ((dep.f & 2) === 0 || (dep.f & 65536) === 0) continue;
			dep.f ^= WAS_MARKED;
			clear_marked(
				/** @type {Derived} */
				dep.deps
			);
		}
	}
	/**
	* @param {Effect} effect
	* @param {Set<Effect>} dirty_effects
	* @param {Set<Effect>} maybe_dirty_effects
	*/
	function defer_effect(effect, dirty_effects, maybe_dirty_effects) {
		if ((effect.f & 2048) !== 0) dirty_effects.add(effect);
		else if ((effect.f & 4096) !== 0) maybe_dirty_effects.add(effect);
		clear_marked(effect.deps);
		set_signal_status(effect, CLEAN);
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/reactivity/store.js
	/**
	* We set this to `true` when updating a store so that we correctly
	* schedule effects if the update takes place inside a `$:` effect
	*/
	var legacy_is_updating_store = false;
	/**
	* Whether or not the prop currently being read is a store binding, as in
	* `<Child bind:x={$y} />`. If it is, we treat the prop as mutable even in
	* runes mode, and skip `binding_property_non_reactive` validation
	*/
	var is_store_binding = false;
	/**
	* Returns a tuple that indicates whether `fn()` reads a prop that is a store binding.
	* Used to prevent `binding_property_non_reactive` validation false positives and
	* ensure that these props are treated as mutable even in runes mode
	* @template T
	* @param {() => T} fn
	* @returns {[T, boolean]}
	*/
	function capture_store_binding(fn) {
		var previous_is_store_binding = is_store_binding;
		try {
			is_store_binding = false;
			return [fn(), is_store_binding];
		} finally {
			is_store_binding = previous_is_store_binding;
		}
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/reactivity/batch.js
	/** @import { Fork } from 'svelte' */
	/** @import { Derived, Effect, Reaction, Source, Value } from '#client' */
	/** @type {Set<Batch>} */
	var batches = /* @__PURE__ */ new Set();
	/** @type {Batch | null} */
	var current_batch = null;
	/**
	* This is needed to avoid overwriting inputs
	* @type {Batch | null}
	*/
	var previous_batch = null;
	/**
	* When time travelling (i.e. working in one batch, while other batches
	* still have ongoing work), we ignore the real values of affected
	* signals in favour of their values within the batch
	* @type {Map<Value, any> | null}
	*/
	var batch_values = null;
	/** @type {Effect | null} */
	var last_scheduled_effect = null;
	var is_flushing_sync = false;
	var is_processing = false;
	/**
	* During traversal, this is an array. Newly created effects are (if not immediately
	* executed) pushed to this array, rather than going through the scheduling
	* rigamarole that would cause another turn of the flush loop.
	* @type {Effect[] | null}
	*/
	var collected_effects = null;
	/**
	* An array of effects that are marked during traversal as a result of a `set`
	* (not `internal_set`) call. These will be added to the next batch and
	* trigger another `batch.process()`
	* @type {Effect[] | null}
	* @deprecated when we get rid of legacy mode and stores, we can get rid of this
	*/
	var legacy_updates = null;
	var flush_count = 0;
	var uid = 1;
	var Batch = class Batch {
		id = uid++;
		/**
		* The current values of any signals that are updated in this batch.
		* Tuple format: [value, is_derived] (note: is_derived is false for deriveds, too, if they were overridden via assignment)
		* They keys of this map are identical to `this.#previous`
		* @type {Map<Value, [any, boolean]>}
		*/
		current = /* @__PURE__ */ new Map();
		/**
		* The values of any signals (sources and deriveds) that are updated in this batch _before_ those updates took place.
		* They keys of this map are identical to `this.#current`
		* @type {Map<Value, any>}
		*/
		previous = /* @__PURE__ */ new Map();
		/**
		* When the batch is committed (and the DOM is updated), we need to remove old branches
		* and append new ones by calling the functions added inside (if/each/key/etc) blocks
		* @type {Set<(batch: Batch) => void>}
		*/
		#commit_callbacks = /* @__PURE__ */ new Set();
		/**
		* If a fork is discarded, we need to destroy any effects that are no longer needed
		* @type {Set<(batch: Batch) => void>}
		*/
		#discard_callbacks = /* @__PURE__ */ new Set();
		/**
		* Callbacks that should run only when a fork is committed.
		* @type {Set<(batch: Batch) => void>}
		*/
		#fork_commit_callbacks = /* @__PURE__ */ new Set();
		/**
		* Async effects that are currently in flight
		* @type {Map<Effect, number>}
		*/
		#pending = /* @__PURE__ */ new Map();
		/**
		* Async effects that are currently in flight, _not_ inside a pending boundary
		* @type {Map<Effect, number>}
		*/
		#blocking_pending = /* @__PURE__ */ new Map();
		/**
		* A deferred that resolves when the batch is committed, used with `settled()`
		* TODO replace with Promise.withResolvers once supported widely enough
		* @type {{ promise: Promise<void>, resolve: (value?: any) => void, reject: (reason: unknown) => void } | null}
		*/
		#deferred = null;
		/**
		* The root effects that need to be flushed
		* @type {Effect[]}
		*/
		#roots = [];
		/**
		* Effects created while this batch was active.
		* @type {Effect[]}
		*/
		#new_effects = [];
		/**
		* Deferred effects (which run after async work has completed) that are DIRTY
		* @type {Set<Effect>}
		*/
		#dirty_effects = /* @__PURE__ */ new Set();
		/**
		* Deferred effects that are MAYBE_DIRTY
		* @type {Set<Effect>}
		*/
		#maybe_dirty_effects = /* @__PURE__ */ new Set();
		/**
		* A map of branches that still exist, but will be destroyed when this batch
		* is committed — we skip over these during `process`.
		* The value contains child effects that were dirty/maybe_dirty before being reset,
		* so they can be rescheduled if the branch survives.
		* @type {Map<Effect, { d: Effect[], m: Effect[] }>}
		*/
		#skipped_branches = /* @__PURE__ */ new Map();
		/**
		* Inverse of #skipped_branches which we need to tell prior batches to unskip them when committing
		* @type {Set<Effect>}
		*/
		#unskipped_branches = /* @__PURE__ */ new Set();
		is_fork = false;
		#decrement_queued = false;
		/** @type {Set<Batch>} */
		#blockers = /* @__PURE__ */ new Set();
		#is_deferred() {
			return this.is_fork || this.#blocking_pending.size > 0;
		}
		#is_blocked() {
			for (const batch of this.#blockers) for (const effect of batch.#blocking_pending.keys()) {
				var skipped = false;
				var e = effect;
				while (e.parent !== null) {
					if (this.#skipped_branches.has(e)) {
						skipped = true;
						break;
					}
					e = e.parent;
				}
				if (!skipped) return true;
			}
			return false;
		}
		/**
		* Add an effect to the #skipped_branches map and reset its children
		* @param {Effect} effect
		*/
		skip_effect(effect) {
			if (!this.#skipped_branches.has(effect)) this.#skipped_branches.set(effect, {
				d: [],
				m: []
			});
			this.#unskipped_branches.delete(effect);
		}
		/**
		* Remove an effect from the #skipped_branches map and reschedule
		* any tracked dirty/maybe_dirty child effects
		* @param {Effect} effect
		* @param {(e: Effect) => void} callback
		*/
		unskip_effect(effect, callback = (e) => this.schedule(e)) {
			var tracked = this.#skipped_branches.get(effect);
			if (tracked) {
				this.#skipped_branches.delete(effect);
				for (var e of tracked.d) {
					set_signal_status(e, DIRTY);
					callback(e);
				}
				for (e of tracked.m) {
					set_signal_status(e, MAYBE_DIRTY);
					callback(e);
				}
			}
			this.#unskipped_branches.add(effect);
		}
		#process() {
			if (flush_count++ > 1e3) {
				batches.delete(this);
				infinite_loop_guard();
			}
			if (!this.#is_deferred()) {
				for (const e of this.#dirty_effects) {
					this.#maybe_dirty_effects.delete(e);
					set_signal_status(e, DIRTY);
					this.schedule(e);
				}
				for (const e of this.#maybe_dirty_effects) {
					set_signal_status(e, MAYBE_DIRTY);
					this.schedule(e);
				}
			}
			const roots = this.#roots;
			this.#roots = [];
			this.apply();
			/** @type {Effect[]} */
			var effects = collected_effects = [];
			/** @type {Effect[]} */
			var render_effects = [];
			/**
			* @type {Effect[]}
			* @deprecated when we get rid of legacy mode and stores, we can get rid of this
			*/
			var updates = legacy_updates = [];
			for (const root of roots) try {
				this.#traverse(root, effects, render_effects);
			} catch (e) {
				reset_all(root);
				throw e;
			}
			current_batch = null;
			if (updates.length > 0) {
				var batch = Batch.ensure();
				for (const e of updates) batch.schedule(e);
			}
			collected_effects = null;
			legacy_updates = null;
			if (this.#is_deferred() || this.#is_blocked()) {
				this.#defer_effects(render_effects);
				this.#defer_effects(effects);
				for (const [e, t] of this.#skipped_branches) reset_branch(e, t);
			} else {
				if (this.#pending.size === 0) batches.delete(this);
				this.#dirty_effects.clear();
				this.#maybe_dirty_effects.clear();
				for (const fn of this.#commit_callbacks) fn(this);
				this.#commit_callbacks.clear();
				previous_batch = this;
				flush_queued_effects(render_effects);
				flush_queued_effects(effects);
				previous_batch = null;
				this.#deferred?.resolve();
			}
			var next_batch = current_batch;
			if (this.#roots.length > 0) {
				const batch = next_batch ??= this;
				batch.#roots.push(...this.#roots.filter((r) => !batch.#roots.includes(r)));
			}
			if (next_batch !== null) {
				batches.add(next_batch);
				next_batch.#process();
			}
			if (async_mode_flag && !batches.has(this)) this.#commit();
		}
		/**
		* Traverse the effect tree, executing effects or stashing
		* them for later execution as appropriate
		* @param {Effect} root
		* @param {Effect[]} effects
		* @param {Effect[]} render_effects
		*/
		#traverse(root, effects, render_effects) {
			root.f ^= CLEAN;
			var effect = root.first;
			while (effect !== null) {
				var flags = effect.f;
				var is_branch = (flags & 96) !== 0;
				if (!(is_branch && (flags & 1024) !== 0 || (flags & 8192) !== 0 || this.#skipped_branches.has(effect)) && effect.fn !== null) {
					if (is_branch) effect.f ^= CLEAN;
					else if ((flags & 4) !== 0) effects.push(effect);
					else if (async_mode_flag && (flags & 16777224) !== 0) render_effects.push(effect);
					else if (is_dirty(effect)) {
						if ((flags & 16) !== 0) this.#maybe_dirty_effects.add(effect);
						update_effect(effect);
					}
					var child = effect.first;
					if (child !== null) {
						effect = child;
						continue;
					}
				}
				while (effect !== null) {
					var next = effect.next;
					if (next !== null) {
						effect = next;
						break;
					}
					effect = effect.parent;
				}
			}
		}
		/**
		* @param {Effect[]} effects
		*/
		#defer_effects(effects) {
			for (var i = 0; i < effects.length; i += 1) defer_effect(effects[i], this.#dirty_effects, this.#maybe_dirty_effects);
		}
		/**
		* Associate a change to a given source with the current
		* batch, noting its previous and current values
		* @param {Value} source
		* @param {any} value
		* @param {boolean} [is_derived]
		*/
		capture(source, value, is_derived = false) {
			if (source.v !== UNINITIALIZED && !this.previous.has(source)) this.previous.set(source, source.v);
			if ((source.f & 8388608) === 0) {
				this.current.set(source, [value, is_derived]);
				batch_values?.set(source, value);
			}
			if (!this.is_fork) source.v = value;
		}
		activate() {
			current_batch = this;
		}
		deactivate() {
			current_batch = null;
			batch_values = null;
		}
		flush() {
			try {
				is_processing = true;
				current_batch = this;
				this.#process();
			} finally {
				flush_count = 0;
				last_scheduled_effect = null;
				collected_effects = null;
				legacy_updates = null;
				is_processing = false;
				current_batch = null;
				batch_values = null;
				old_values.clear();
			}
		}
		discard() {
			for (const fn of this.#discard_callbacks) fn(this);
			this.#discard_callbacks.clear();
			this.#fork_commit_callbacks.clear();
			batches.delete(this);
		}
		/**
		* @param {Effect} effect
		*/
		register_created_effect(effect) {
			this.#new_effects.push(effect);
		}
		#commit() {
			for (const batch of batches) {
				var is_earlier = batch.id < this.id;
				/** @type {Source[]} */
				var sources = [];
				for (const [source, [value, is_derived]] of this.current) {
					if (batch.current.has(source)) {
						var batch_value = batch.current.get(source)[0];
						if (is_earlier && value !== batch_value) batch.current.set(source, [value, is_derived]);
						else continue;
					}
					sources.push(source);
				}
				var others = [...batch.current.keys()].filter((s) => !this.current.has(s));
				if (others.length === 0) {
					if (is_earlier) batch.discard();
				} else if (sources.length > 0) {
					if (is_earlier) for (const unskipped of this.#unskipped_branches) batch.unskip_effect(unskipped, (e) => {
						if ((e.f & 4194320) !== 0) batch.schedule(e);
						else batch.#defer_effects([e]);
					});
					batch.activate();
					/** @type {Set<Value>} */
					var marked = /* @__PURE__ */ new Set();
					/** @type {Map<Reaction, boolean>} */
					var checked = /* @__PURE__ */ new Map();
					for (var source of sources) mark_effects(source, others, marked, checked);
					checked = /* @__PURE__ */ new Map();
					var current_unequal = [...batch.current.keys()].filter((c) => this.current.has(c) ? this.current.get(c)[0] !== c : true);
					for (const effect of this.#new_effects) if ((effect.f & 155648) === 0 && depends_on(effect, current_unequal, checked)) if ((effect.f & 4194320) !== 0) {
						set_signal_status(effect, DIRTY);
						batch.schedule(effect);
					} else batch.#dirty_effects.add(effect);
					if (batch.#roots.length > 0) {
						batch.apply();
						for (var root of batch.#roots) batch.#traverse(root, [], []);
						batch.#roots = [];
					}
					batch.deactivate();
				}
			}
			for (const batch of batches) if (batch.#blockers.has(this)) {
				batch.#blockers.delete(this);
				if (batch.#blockers.size === 0 && !batch.#is_deferred()) {
					batch.activate();
					batch.#process();
				}
			}
		}
		/**
		* @param {boolean} blocking
		* @param {Effect} effect
		*/
		increment(blocking, effect) {
			let pending_count = this.#pending.get(effect) ?? 0;
			this.#pending.set(effect, pending_count + 1);
			if (blocking) {
				let blocking_pending_count = this.#blocking_pending.get(effect) ?? 0;
				this.#blocking_pending.set(effect, blocking_pending_count + 1);
			}
		}
		/**
		* @param {boolean} blocking
		* @param {Effect} effect
		* @param {boolean} skip - whether to skip updates (because this is triggered by a stale reaction)
		*/
		decrement(blocking, effect, skip) {
			let pending_count = this.#pending.get(effect) ?? 0;
			if (pending_count === 1) this.#pending.delete(effect);
			else this.#pending.set(effect, pending_count - 1);
			if (blocking) {
				let blocking_pending_count = this.#blocking_pending.get(effect) ?? 0;
				if (blocking_pending_count === 1) this.#blocking_pending.delete(effect);
				else this.#blocking_pending.set(effect, blocking_pending_count - 1);
			}
			if (this.#decrement_queued || skip) return;
			this.#decrement_queued = true;
			queue_micro_task(() => {
				this.#decrement_queued = false;
				this.flush();
			});
		}
		/**
		* @param {Set<Effect>} dirty_effects
		* @param {Set<Effect>} maybe_dirty_effects
		*/
		transfer_effects(dirty_effects, maybe_dirty_effects) {
			for (const e of dirty_effects) this.#dirty_effects.add(e);
			for (const e of maybe_dirty_effects) this.#maybe_dirty_effects.add(e);
			dirty_effects.clear();
			maybe_dirty_effects.clear();
		}
		/** @param {(batch: Batch) => void} fn */
		oncommit(fn) {
			this.#commit_callbacks.add(fn);
		}
		/** @param {(batch: Batch) => void} fn */
		ondiscard(fn) {
			this.#discard_callbacks.add(fn);
		}
		/** @param {(batch: Batch) => void} fn */
		on_fork_commit(fn) {
			this.#fork_commit_callbacks.add(fn);
		}
		run_fork_commit_callbacks() {
			for (const fn of this.#fork_commit_callbacks) fn(this);
			this.#fork_commit_callbacks.clear();
		}
		settled() {
			return (this.#deferred ??= deferred()).promise;
		}
		static ensure() {
			if (current_batch === null) {
				const batch = current_batch = new Batch();
				if (!is_processing) {
					batches.add(current_batch);
					if (!is_flushing_sync) queue_micro_task(() => {
						if (current_batch !== batch) return;
						batch.flush();
					});
				}
			}
			return current_batch;
		}
		apply() {
			if (!async_mode_flag || !this.is_fork && batches.size === 1) {
				batch_values = null;
				return;
			}
			batch_values = /* @__PURE__ */ new Map();
			for (const [source, [value]] of this.current) batch_values.set(source, value);
			for (const batch of batches) {
				if (batch === this || batch.is_fork) continue;
				var intersects = false;
				var differs = false;
				if (batch.id < this.id) for (const [source, [, is_derived]] of batch.current) {
					if (is_derived) continue;
					intersects ||= this.current.has(source);
					differs ||= !this.current.has(source);
				}
				if (intersects && differs) this.#blockers.add(batch);
				else for (const [source, previous] of batch.previous) if (!batch_values.has(source)) batch_values.set(source, previous);
			}
		}
		/**
		*
		* @param {Effect} effect
		*/
		schedule(effect) {
			last_scheduled_effect = effect;
			if (effect.b?.is_pending && (effect.f & 16777228) !== 0 && (effect.f & 32768) === 0) {
				effect.b.defer_effect(effect);
				return;
			}
			var e = effect;
			while (e.parent !== null) {
				e = e.parent;
				var flags = e.f;
				if (collected_effects !== null && e === active_effect) {
					if (async_mode_flag) return;
					if ((active_reaction === null || (active_reaction.f & 2) === 0) && !legacy_is_updating_store) return;
				}
				if ((flags & 96) !== 0) {
					if ((flags & 1024) === 0) return;
					e.f ^= CLEAN;
				}
			}
			this.#roots.push(e);
		}
	};
	/**
	* Synchronously flush any pending updates.
	* Returns void if no callback is provided, otherwise returns the result of calling the callback.
	* @template [T=void]
	* @param {(() => T) | undefined} [fn]
	* @returns {T}
	*/
	function flushSync(fn) {
		var was_flushing_sync = is_flushing_sync;
		is_flushing_sync = true;
		try {
			var result;
			if (fn) {
				if (current_batch !== null && !current_batch.is_fork) current_batch.flush();
				result = fn();
			}
			while (true) {
				flush_tasks();
				if (current_batch === null) return result;
				current_batch.flush();
			}
		} finally {
			is_flushing_sync = was_flushing_sync;
		}
	}
	function infinite_loop_guard() {
		try {
			effect_update_depth_exceeded();
		} catch (error) {
			invoke_error_boundary(error, last_scheduled_effect);
		}
	}
	/** @type {Set<Effect> | null} */
	var eager_block_effects = null;
	/**
	* @param {Array<Effect>} effects
	* @returns {void}
	*/
	function flush_queued_effects(effects) {
		var length = effects.length;
		if (length === 0) return;
		var i = 0;
		while (i < length) {
			var effect = effects[i++];
			if ((effect.f & 24576) === 0 && is_dirty(effect)) {
				eager_block_effects = /* @__PURE__ */ new Set();
				update_effect(effect);
				if (effect.deps === null && effect.first === null && effect.nodes === null && effect.teardown === null && effect.ac === null) unlink_effect(effect);
				if (eager_block_effects?.size > 0) {
					old_values.clear();
					for (const e of eager_block_effects) {
						if ((e.f & 24576) !== 0) continue;
						/** @type {Effect[]} */
						const ordered_effects = [e];
						let ancestor = e.parent;
						while (ancestor !== null) {
							if (eager_block_effects.has(ancestor)) {
								eager_block_effects.delete(ancestor);
								ordered_effects.push(ancestor);
							}
							ancestor = ancestor.parent;
						}
						for (let j = ordered_effects.length - 1; j >= 0; j--) {
							const e = ordered_effects[j];
							if ((e.f & 24576) !== 0) continue;
							update_effect(e);
						}
					}
					eager_block_effects.clear();
				}
			}
		}
		eager_block_effects = null;
	}
	/**
	* This is similar to `mark_reactions`, but it only marks async/block effects
	* depending on `value` and at least one of the other `sources`, so that
	* these effects can re-run after another batch has been committed
	* @param {Value} value
	* @param {Source[]} sources
	* @param {Set<Value>} marked
	* @param {Map<Reaction, boolean>} checked
	*/
	function mark_effects(value, sources, marked, checked) {
		if (marked.has(value)) return;
		marked.add(value);
		if (value.reactions !== null) for (const reaction of value.reactions) {
			const flags = reaction.f;
			if ((flags & 2) !== 0) mark_effects(reaction, sources, marked, checked);
			else if ((flags & 4194320) !== 0 && (flags & 2048) === 0 && depends_on(reaction, sources, checked)) {
				set_signal_status(reaction, DIRTY);
				schedule_effect(reaction);
			}
		}
	}
	/**
	* @param {Reaction} reaction
	* @param {Source[]} sources
	* @param {Map<Reaction, boolean>} checked
	*/
	function depends_on(reaction, sources, checked) {
		const depends = checked.get(reaction);
		if (depends !== void 0) return depends;
		if (reaction.deps !== null) for (const dep of reaction.deps) {
			if (includes.call(sources, dep)) return true;
			if ((dep.f & 2) !== 0 && depends_on(dep, sources, checked)) {
				checked.set(dep, true);
				return true;
			}
		}
		checked.set(reaction, false);
		return false;
	}
	/**
	* @param {Effect} effect
	* @returns {void}
	*/
	function schedule_effect(effect) {
		/** @type {Batch} */ current_batch.schedule(effect);
	}
	/**
	* Mark all the effects inside a skipped branch CLEAN, so that
	* they can be correctly rescheduled later. Tracks dirty and maybe_dirty
	* effects so they can be rescheduled if the branch survives.
	* @param {Effect} effect
	* @param {{ d: Effect[], m: Effect[] }} tracked
	*/
	function reset_branch(effect, tracked) {
		if ((effect.f & 32) !== 0 && (effect.f & 1024) !== 0) return;
		if ((effect.f & 2048) !== 0) tracked.d.push(effect);
		else if ((effect.f & 4096) !== 0) tracked.m.push(effect);
		set_signal_status(effect, CLEAN);
		var e = effect.first;
		while (e !== null) {
			reset_branch(e, tracked);
			e = e.next;
		}
	}
	/**
	* Mark an entire effect tree clean following an error
	* @param {Effect} effect
	*/
	function reset_all(effect) {
		set_signal_status(effect, CLEAN);
		var e = effect.first;
		while (e !== null) {
			reset_all(e);
			e = e.next;
		}
	}
	//#endregion
	//#region node_modules/svelte/src/reactivity/create-subscriber.js
	/**
	* Returns a `subscribe` function that integrates external event-based systems with Svelte's reactivity.
	* It's particularly useful for integrating with web APIs like `MediaQuery`, `IntersectionObserver`, or `WebSocket`.
	*
	* If `subscribe` is called inside an effect (including indirectly, for example inside a getter),
	* the `start` callback will be called with an `update` function. Whenever `update` is called, the effect re-runs.
	*
	* If `start` returns a cleanup function, it will be called when the effect is destroyed.
	*
	* If `subscribe` is called in multiple effects, `start` will only be called once as long as the effects
	* are active, and the returned teardown function will only be called when all effects are destroyed.
	*
	* It's best understood with an example. Here's an implementation of [`MediaQuery`](https://svelte.dev/docs/svelte/svelte-reactivity#MediaQuery):
	*
	* ```js
	* import { createSubscriber } from 'svelte/reactivity';
	* import { on } from 'svelte/events';
	*
	* export class MediaQuery {
	* 	#query;
	* 	#subscribe;
	*
	* 	constructor(query) {
	* 		this.#query = window.matchMedia(`(${query})`);
	*
	* 		this.#subscribe = createSubscriber((update) => {
	* 			// when the `change` event occurs, re-run any effects that read `this.current`
	* 			const off = on(this.#query, 'change', update);
	*
	* 			// stop listening when all the effects are destroyed
	* 			return () => off();
	* 		});
	* 	}
	*
	* 	get current() {
	* 		// This makes the getter reactive, if read in an effect
	* 		this.#subscribe();
	*
	* 		// Return the current state of the query, whether or not we're in an effect
	* 		return this.#query.matches;
	* 	}
	* }
	* ```
	* @param {(update: () => void) => (() => void) | void} start
	* @since 5.7.0
	*/
	function createSubscriber(start) {
		let subscribers = 0;
		let version = source(0);
		/** @type {(() => void) | void} */
		let stop;
		return () => {
			if (effect_tracking()) {
				get(version);
				render_effect(() => {
					if (subscribers === 0) stop = untrack(() => start(() => increment(version)));
					subscribers += 1;
					return () => {
						queue_micro_task(() => {
							subscribers -= 1;
							if (subscribers === 0) {
								stop?.();
								stop = void 0;
								increment(version);
							}
						});
					};
				});
			}
		};
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/dom/blocks/boundary.js
	/** @import { Effect, Source, TemplateNode, } from '#client' */
	/**
	* @typedef {{
	* 	 onerror?: (error: unknown, reset: () => void) => void;
	*   failed?: (anchor: Node, error: () => unknown, reset: () => () => void) => void;
	*   pending?: (anchor: Node) => void;
	* }} BoundaryProps
	*/
	var flags = EFFECT_TRANSPARENT | EFFECT_PRESERVED;
	/**
	* @param {TemplateNode} node
	* @param {BoundaryProps} props
	* @param {((anchor: Node) => void)} children
	* @param {((error: unknown) => unknown) | undefined} [transform_error]
	* @returns {void}
	*/
	function boundary(node, props, children, transform_error) {
		new Boundary(node, props, children, transform_error);
	}
	var Boundary = class {
		/** @type {Boundary | null} */
		parent;
		is_pending = false;
		/**
		* API-level transformError transform function. Transforms errors before they reach the `failed` snippet.
		* Inherited from parent boundary, or defaults to identity.
		* @type {(error: unknown) => unknown}
		*/
		transform_error;
		/** @type {TemplateNode} */
		#anchor;
		/** @type {TemplateNode | null} */
		#hydrate_open = hydrating ? hydrate_node : null;
		/** @type {BoundaryProps} */
		#props;
		/** @type {((anchor: Node) => void)} */
		#children;
		/** @type {Effect} */
		#effect;
		/** @type {Effect | null} */
		#main_effect = null;
		/** @type {Effect | null} */
		#pending_effect = null;
		/** @type {Effect | null} */
		#failed_effect = null;
		/** @type {DocumentFragment | null} */
		#offscreen_fragment = null;
		#local_pending_count = 0;
		#pending_count = 0;
		#pending_count_update_queued = false;
		/** @type {Set<Effect>} */
		#dirty_effects = /* @__PURE__ */ new Set();
		/** @type {Set<Effect>} */
		#maybe_dirty_effects = /* @__PURE__ */ new Set();
		/**
		* A source containing the number of pending async deriveds/expressions.
		* Only created if `$effect.pending()` is used inside the boundary,
		* otherwise updating the source results in needless `Batch.ensure()`
		* calls followed by no-op flushes
		* @type {Source<number> | null}
		*/
		#effect_pending = null;
		#effect_pending_subscriber = createSubscriber(() => {
			this.#effect_pending = source(this.#local_pending_count);
			return () => {
				this.#effect_pending = null;
			};
		});
		/**
		* @param {TemplateNode} node
		* @param {BoundaryProps} props
		* @param {((anchor: Node) => void)} children
		* @param {((error: unknown) => unknown) | undefined} [transform_error]
		*/
		constructor(node, props, children, transform_error) {
			this.#anchor = node;
			this.#props = props;
			this.#children = (anchor) => {
				var effect = active_effect;
				effect.b = this;
				effect.f |= 128;
				children(anchor);
			};
			this.parent = active_effect.b;
			this.transform_error = transform_error ?? this.parent?.transform_error ?? ((e) => e);
			this.#effect = block(() => {
				if (hydrating) {
					const comment = this.#hydrate_open;
					hydrate_next();
					const server_rendered_pending = comment.data === "[!";
					if (comment.data.startsWith("[?")) {
						const serialized_error = JSON.parse(comment.data.slice(2));
						this.#hydrate_failed_content(serialized_error);
					} else if (server_rendered_pending) this.#hydrate_pending_content();
					else this.#hydrate_resolved_content();
				} else this.#render();
			}, flags);
			if (hydrating) this.#anchor = hydrate_node;
		}
		#hydrate_resolved_content() {
			try {
				this.#main_effect = branch(() => this.#children(this.#anchor));
			} catch (error) {
				this.error(error);
			}
		}
		/**
		* @param {unknown} error The deserialized error from the server's hydration comment
		*/
		#hydrate_failed_content(error) {
			const failed = this.#props.failed;
			if (!failed) return;
			this.#failed_effect = branch(() => {
				failed(this.#anchor, () => error, () => () => {});
			});
		}
		#hydrate_pending_content() {
			const pending = this.#props.pending;
			if (!pending) return;
			this.is_pending = true;
			this.#pending_effect = branch(() => pending(this.#anchor));
			queue_micro_task(() => {
				var fragment = this.#offscreen_fragment = document.createDocumentFragment();
				var anchor = create_text();
				fragment.append(anchor);
				this.#main_effect = this.#run(() => {
					return branch(() => this.#children(anchor));
				});
				if (this.#pending_count === 0) {
					this.#anchor.before(fragment);
					this.#offscreen_fragment = null;
					pause_effect(this.#pending_effect, () => {
						this.#pending_effect = null;
					});
					this.#resolve(current_batch);
				}
			});
		}
		#render() {
			try {
				this.is_pending = this.has_pending_snippet();
				this.#pending_count = 0;
				this.#local_pending_count = 0;
				this.#main_effect = branch(() => {
					this.#children(this.#anchor);
				});
				if (this.#pending_count > 0) {
					var fragment = this.#offscreen_fragment = document.createDocumentFragment();
					move_effect(this.#main_effect, fragment);
					const pending = this.#props.pending;
					this.#pending_effect = branch(() => pending(this.#anchor));
				} else this.#resolve(current_batch);
			} catch (error) {
				this.error(error);
			}
		}
		/**
		* @param {Batch} batch
		*/
		#resolve(batch) {
			this.is_pending = false;
			batch.transfer_effects(this.#dirty_effects, this.#maybe_dirty_effects);
		}
		/**
		* Defer an effect inside a pending boundary until the boundary resolves
		* @param {Effect} effect
		*/
		defer_effect(effect) {
			defer_effect(effect, this.#dirty_effects, this.#maybe_dirty_effects);
		}
		/**
		* Returns `false` if the effect exists inside a boundary whose pending snippet is shown
		* @returns {boolean}
		*/
		is_rendered() {
			return !this.is_pending && (!this.parent || this.parent.is_rendered());
		}
		has_pending_snippet() {
			return !!this.#props.pending;
		}
		/**
		* @template T
		* @param {() => T} fn
		*/
		#run(fn) {
			var previous_effect = active_effect;
			var previous_reaction = active_reaction;
			var previous_ctx = component_context;
			set_active_effect(this.#effect);
			set_active_reaction(this.#effect);
			set_component_context(this.#effect.ctx);
			try {
				Batch.ensure();
				return fn();
			} catch (e) {
				handle_error(e);
				return null;
			} finally {
				set_active_effect(previous_effect);
				set_active_reaction(previous_reaction);
				set_component_context(previous_ctx);
			}
		}
		/**
		* Updates the pending count associated with the currently visible pending snippet,
		* if any, such that we can replace the snippet with content once work is done
		* @param {1 | -1} d
		* @param {Batch} batch
		*/
		#update_pending_count(d, batch) {
			if (!this.has_pending_snippet()) {
				if (this.parent) this.parent.#update_pending_count(d, batch);
				return;
			}
			this.#pending_count += d;
			if (this.#pending_count === 0) {
				this.#resolve(batch);
				if (this.#pending_effect) pause_effect(this.#pending_effect, () => {
					this.#pending_effect = null;
				});
				if (this.#offscreen_fragment) {
					this.#anchor.before(this.#offscreen_fragment);
					this.#offscreen_fragment = null;
				}
			}
		}
		/**
		* Update the source that powers `$effect.pending()` inside this boundary,
		* and controls when the current `pending` snippet (if any) is removed.
		* Do not call from inside the class
		* @param {1 | -1} d
		* @param {Batch} batch
		*/
		update_pending_count(d, batch) {
			this.#update_pending_count(d, batch);
			this.#local_pending_count += d;
			if (!this.#effect_pending || this.#pending_count_update_queued) return;
			this.#pending_count_update_queued = true;
			queue_micro_task(() => {
				this.#pending_count_update_queued = false;
				if (this.#effect_pending) internal_set(this.#effect_pending, this.#local_pending_count);
			});
		}
		get_effect_pending() {
			this.#effect_pending_subscriber();
			return get(this.#effect_pending);
		}
		/** @param {unknown} error */
		error(error) {
			if (!this.#props.onerror && !this.#props.failed) throw error;
			if (current_batch?.is_fork) {
				if (this.#main_effect) current_batch.skip_effect(this.#main_effect);
				if (this.#pending_effect) current_batch.skip_effect(this.#pending_effect);
				if (this.#failed_effect) current_batch.skip_effect(this.#failed_effect);
				current_batch.on_fork_commit(() => {
					this.#handle_error(error);
				});
			} else this.#handle_error(error);
		}
		/**
		* @param {unknown} error
		*/
		#handle_error(error) {
			if (this.#main_effect) {
				destroy_effect(this.#main_effect);
				this.#main_effect = null;
			}
			if (this.#pending_effect) {
				destroy_effect(this.#pending_effect);
				this.#pending_effect = null;
			}
			if (this.#failed_effect) {
				destroy_effect(this.#failed_effect);
				this.#failed_effect = null;
			}
			if (hydrating) {
				set_hydrate_node(this.#hydrate_open);
				next();
				set_hydrate_node(skip_nodes());
			}
			var onerror = this.#props.onerror;
			let failed = this.#props.failed;
			var did_reset = false;
			var calling_on_error = false;
			const reset = () => {
				if (did_reset) {
					svelte_boundary_reset_noop();
					return;
				}
				did_reset = true;
				if (calling_on_error) svelte_boundary_reset_onerror();
				if (this.#failed_effect !== null) pause_effect(this.#failed_effect, () => {
					this.#failed_effect = null;
				});
				this.#run(() => {
					this.#render();
				});
			};
			/** @param {unknown} transformed_error */
			const handle_error_result = (transformed_error) => {
				try {
					calling_on_error = true;
					onerror?.(transformed_error, reset);
					calling_on_error = false;
				} catch (error) {
					invoke_error_boundary(error, this.#effect && this.#effect.parent);
				}
				if (failed) this.#failed_effect = this.#run(() => {
					try {
						return branch(() => {
							var effect = active_effect;
							effect.b = this;
							effect.f |= 128;
							failed(this.#anchor, () => transformed_error, () => reset);
						});
					} catch (error) {
						invoke_error_boundary(error, this.#effect.parent);
						return null;
					}
				});
			};
			queue_micro_task(() => {
				/** @type {unknown} */
				var result;
				try {
					result = this.transform_error(error);
				} catch (e) {
					invoke_error_boundary(e, this.#effect && this.#effect.parent);
					return;
				}
				if (result !== null && typeof result === "object" && typeof result.then === "function")
 /** @type {any} */ result.then(
					handle_error_result,
					/** @param {unknown} e */
					(e) => invoke_error_boundary(e, this.#effect && this.#effect.parent)
				);
				else handle_error_result(result);
			});
		}
	};
	//#endregion
	//#region node_modules/svelte/src/internal/client/reactivity/async.js
	/** @import { Blocker, Effect, Value } from '#client' */
	/**
	* @param {Blocker[]} blockers
	* @param {Array<() => any>} sync
	* @param {Array<() => Promise<any>>} async
	* @param {(values: Value[]) => any} fn
	*/
	function flatten(blockers, sync, async, fn) {
		const d = is_runes() ? derived : derived_safe_equal;
		var pending = blockers.filter((b) => !b.settled);
		if (async.length === 0 && pending.length === 0) {
			fn(sync.map(d));
			return;
		}
		var parent = active_effect;
		var restore = capture();
		var blocker_promise = pending.length === 1 ? pending[0].promise : pending.length > 1 ? Promise.all(pending.map((b) => b.promise)) : null;
		/** @param {Value[]} values */
		function finish(values) {
			restore();
			try {
				fn(values);
			} catch (error) {
				if ((parent.f & 16384) === 0) invoke_error_boundary(error, parent);
			}
			unset_context();
		}
		if (async.length === 0) {
			/** @type {Promise<any>} */ blocker_promise.then(() => finish(sync.map(d)));
			return;
		}
		var decrement_pending = increment_pending();
		function run() {
			Promise.all(async.map((expression) => /* @__PURE__ */ async_derived(expression))).then((result) => finish([...sync.map(d), ...result])).catch((error) => invoke_error_boundary(error, parent)).finally(() => decrement_pending());
		}
		if (blocker_promise) blocker_promise.then(() => {
			restore();
			run();
			unset_context();
		});
		else run();
	}
	/**
	* Captures the current effect context so that we can restore it after
	* some asynchronous work has happened (so that e.g. `await a + b`
	* causes `b` to be registered as a dependency).
	*/
	function capture() {
		var previous_effect = active_effect;
		var previous_reaction = active_reaction;
		var previous_component_context = component_context;
		var previous_batch = current_batch;
		return function restore(activate_batch = true) {
			set_active_effect(previous_effect);
			set_active_reaction(previous_reaction);
			set_component_context(previous_component_context);
			if (activate_batch && (previous_effect.f & 16384) === 0) {
				previous_batch?.activate();
				previous_batch?.apply();
			}
		};
	}
	function unset_context(deactivate_batch = true) {
		set_active_effect(null);
		set_active_reaction(null);
		set_component_context(null);
		if (deactivate_batch) current_batch?.deactivate();
	}
	/**
	* @returns {(skip?: boolean) => void}
	*/
	function increment_pending() {
		var effect = active_effect;
		var boundary = effect.b;
		var batch = current_batch;
		var blocking = boundary.is_rendered();
		boundary.update_pending_count(1, batch);
		batch.increment(blocking, effect);
		return (skip = false) => {
			boundary.update_pending_count(-1, batch);
			batch.decrement(blocking, effect, skip);
		};
	}
	/**
	* @template V
	* @param {() => V} fn
	* @returns {Derived<V>}
	*/
	/* @__NO_SIDE_EFFECTS__ */
	function derived(fn) {
		var flags = 2 | DIRTY;
		if (active_effect !== null) active_effect.f |= EFFECT_PRESERVED;
		return {
			ctx: component_context,
			deps: null,
			effects: null,
			equals,
			f: flags,
			fn,
			reactions: null,
			rv: 0,
			v: UNINITIALIZED,
			wv: 0,
			parent: active_effect,
			ac: null
		};
	}
	/**
	* @template V
	* @param {() => V | Promise<V>} fn
	* @param {string} [label]
	* @param {string} [location] If provided, print a warning if the value is not read immediately after update
	* @returns {Promise<Source<V>>}
	*/
	/* @__NO_SIDE_EFFECTS__ */
	function async_derived(fn, label, location) {
		let parent = active_effect;
		if (parent === null) async_derived_orphan();
		var promise = void 0;
		var signal = source(UNINITIALIZED);
		var should_suspend = !active_reaction;
		/** @type {Map<Batch, ReturnType<typeof deferred<V>>>} */
		var deferreds = /* @__PURE__ */ new Map();
		async_effect(() => {
			var effect = active_effect;
			/** @type {ReturnType<typeof deferred<V>>} */
			var d = deferred();
			promise = d.promise;
			try {
				Promise.resolve(fn()).then(d.resolve, d.reject).finally(unset_context);
			} catch (error) {
				d.reject(error);
				unset_context();
			}
			var batch = current_batch;
			if (should_suspend) {
				if ((effect.f & 32768) !== 0) var decrement_pending = increment_pending();
				if (parent.b.is_rendered()) {
					deferreds.get(batch)?.reject(STALE_REACTION);
					deferreds.delete(batch);
				} else {
					for (const d of deferreds.values()) d.reject(STALE_REACTION);
					deferreds.clear();
				}
				deferreds.set(batch, d);
			}
			/**
			* @param {any} value
			* @param {unknown} error
			*/
			const handler = (value, error = void 0) => {
				if (decrement_pending) decrement_pending(error === STALE_REACTION);
				if (error === STALE_REACTION || (effect.f & 16384) !== 0) return;
				batch.activate();
				if (error) {
					signal.f |= ERROR_VALUE;
					internal_set(signal, error);
				} else {
					if ((signal.f & 8388608) !== 0) signal.f ^= ERROR_VALUE;
					internal_set(signal, value);
					for (const [b, d] of deferreds) {
						deferreds.delete(b);
						if (b === batch) break;
						d.reject(STALE_REACTION);
					}
				}
				batch.deactivate();
			};
			d.promise.then(handler, (e) => handler(null, e || "unknown"));
		});
		teardown(() => {
			for (const d of deferreds.values()) d.reject(STALE_REACTION);
		});
		return new Promise((fulfil) => {
			/** @param {Promise<V>} p */
			function next(p) {
				function go() {
					if (p === promise) fulfil(signal);
					else next(promise);
				}
				p.then(go, go);
			}
			next(promise);
		});
	}
	/**
	* @template V
	* @param {() => V} fn
	* @returns {Derived<V>}
	*/
	/* @__NO_SIDE_EFFECTS__ */
	function user_derived(fn) {
		const d = /* @__PURE__ */ derived(fn);
		if (!async_mode_flag) push_reaction_value(d);
		return d;
	}
	/**
	* @template V
	* @param {() => V} fn
	* @returns {Derived<V>}
	*/
	/* @__NO_SIDE_EFFECTS__ */
	function derived_safe_equal(fn) {
		const signal = /* @__PURE__ */ derived(fn);
		signal.equals = safe_equals;
		return signal;
	}
	/**
	* @param {Derived} derived
	* @returns {void}
	*/
	function destroy_derived_effects(derived) {
		var effects = derived.effects;
		if (effects !== null) {
			derived.effects = null;
			for (var i = 0; i < effects.length; i += 1) destroy_effect(effects[i]);
		}
	}
	/**
	* @template T
	* @param {Derived} derived
	* @returns {T}
	*/
	function execute_derived(derived) {
		var value;
		var prev_active_effect = active_effect;
		var parent = derived.parent;
		if (!is_destroying_effect && parent !== null && (parent.f & 24576) !== 0) {
			derived_inert();
			return derived.v;
		}
		set_active_effect(parent);
		try {
			derived.f &= ~WAS_MARKED;
			destroy_derived_effects(derived);
			value = update_reaction(derived);
		} finally {
			set_active_effect(prev_active_effect);
		}
		return value;
	}
	/**
	* @param {Derived} derived
	* @returns {void}
	*/
	function update_derived(derived) {
		var value = execute_derived(derived);
		if (!derived.equals(value)) {
			derived.wv = increment_write_version();
			if (!current_batch?.is_fork || derived.deps === null) {
				if (current_batch !== null) current_batch.capture(derived, value, true);
				else derived.v = value;
				if (derived.deps === null) {
					set_signal_status(derived, CLEAN);
					return;
				}
			}
		}
		if (is_destroying_effect) return;
		if (batch_values !== null) {
			if (effect_tracking() || current_batch?.is_fork) batch_values.set(derived, value);
		} else update_derived_status(derived);
	}
	/**
	* @param {Derived} derived
	*/
	function freeze_derived_effects(derived) {
		if (derived.effects === null) return;
		for (const e of derived.effects) if (e.teardown || e.ac) {
			e.teardown?.();
			e.ac?.abort(STALE_REACTION);
			e.teardown = noop;
			e.ac = null;
			remove_reactions(e, 0);
			destroy_effect_children(e);
		}
	}
	/**
	* @param {Derived} derived
	*/
	function unfreeze_derived_effects(derived) {
		if (derived.effects === null) return;
		for (const e of derived.effects) if (e.teardown) update_effect(e);
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/reactivity/sources.js
	/** @import { Derived, Effect, Source, Value } from '#client' */
	/** @type {Set<any>} */
	var eager_effects = /* @__PURE__ */ new Set();
	/** @type {Map<Source, any>} */
	var old_values = /* @__PURE__ */ new Map();
	var eager_effects_deferred = false;
	/**
	* @template V
	* @param {V} v
	* @param {Error | null} [stack]
	* @returns {Source<V>}
	*/
	function source(v, stack) {
		return {
			f: 0,
			v,
			reactions: null,
			equals,
			rv: 0,
			wv: 0
		};
	}
	/**
	* @template V
	* @param {V} v
	* @param {Error | null} [stack]
	*/
	/* @__NO_SIDE_EFFECTS__ */
	function state(v, stack) {
		const s = source(v, stack);
		push_reaction_value(s);
		return s;
	}
	/**
	* @template V
	* @param {V} initial_value
	* @param {boolean} [immutable]
	* @returns {Source<V>}
	*/
	/* @__NO_SIDE_EFFECTS__ */
	function mutable_source(initial_value, immutable = false, trackable = true) {
		const s = source(initial_value);
		if (!immutable) s.equals = safe_equals;
		if (legacy_mode_flag && trackable && component_context !== null && component_context.l !== null) (component_context.l.s ??= []).push(s);
		return s;
	}
	/**
	* @template V
	* @param {Value<V>} source
	* @param {V} value
	*/
	function mutate(source, value) {
		set(source, untrack(() => get(source)));
		return value;
	}
	/**
	* @template V
	* @param {Source<V>} source
	* @param {V} value
	* @param {boolean} [should_proxy]
	* @returns {V}
	*/
	function set(source, value, should_proxy = false) {
		if (active_reaction !== null && (!untracking || (active_reaction.f & 131072) !== 0) && is_runes() && (active_reaction.f & 4325394) !== 0 && (current_sources === null || !includes.call(current_sources, source))) state_unsafe_mutation();
		return internal_set(source, should_proxy ? proxy(value) : value, legacy_updates);
	}
	/**
	* @template V
	* @param {Source<V>} source
	* @param {V} value
	* @param {Effect[] | null} [updated_during_traversal]
	* @returns {V}
	*/
	function internal_set(source, value, updated_during_traversal = null) {
		if (!source.equals(value)) {
			old_values.set(source, is_destroying_effect ? value : source.v);
			var batch = Batch.ensure();
			batch.capture(source, value);
			if ((source.f & 2) !== 0) {
				const derived = source;
				if ((source.f & 2048) !== 0) execute_derived(derived);
				if (batch_values === null) update_derived_status(derived);
			}
			source.wv = increment_write_version();
			mark_reactions(source, DIRTY, updated_during_traversal);
			if (is_runes() && active_effect !== null && (active_effect.f & 1024) !== 0 && (active_effect.f & 96) === 0) if (untracked_writes === null) set_untracked_writes([source]);
			else untracked_writes.push(source);
			if (!batch.is_fork && eager_effects.size > 0 && !eager_effects_deferred) flush_eager_effects();
		}
		return value;
	}
	function flush_eager_effects() {
		eager_effects_deferred = false;
		for (const effect of eager_effects) {
			if ((effect.f & 1024) !== 0) set_signal_status(effect, MAYBE_DIRTY);
			if (is_dirty(effect)) update_effect(effect);
		}
		eager_effects.clear();
	}
	/**
	* @template {number | bigint} T
	* @param {Source<T>} source
	* @param {1 | -1} [d]
	* @returns {T}
	*/
	function update(source, d = 1) {
		var value = get(source);
		var result = d === 1 ? value++ : value--;
		set(source, value);
		return result;
	}
	/**
	* Silently (without using `get`) increment a source
	* @param {Source<number>} source
	*/
	function increment(source) {
		set(source, source.v + 1);
	}
	/**
	* @param {Value} signal
	* @param {number} status should be DIRTY or MAYBE_DIRTY
	* @param {Effect[] | null} updated_during_traversal
	* @returns {void}
	*/
	function mark_reactions(signal, status, updated_during_traversal) {
		var reactions = signal.reactions;
		if (reactions === null) return;
		var runes = is_runes();
		var length = reactions.length;
		for (var i = 0; i < length; i++) {
			var reaction = reactions[i];
			var flags = reaction.f;
			if (!runes && reaction === active_effect) continue;
			var not_dirty = (flags & DIRTY) === 0;
			if (not_dirty) set_signal_status(reaction, status);
			if ((flags & 2) !== 0) {
				var derived = reaction;
				batch_values?.delete(derived);
				if ((flags & 65536) === 0) {
					if (flags & 512 && (active_effect === null || (active_effect.f & 2097152) === 0)) reaction.f |= WAS_MARKED;
					mark_reactions(derived, MAYBE_DIRTY, updated_during_traversal);
				}
			} else if (not_dirty) {
				var effect = reaction;
				if ((flags & 16) !== 0 && eager_block_effects !== null) eager_block_effects.add(effect);
				if (updated_during_traversal !== null) updated_during_traversal.push(effect);
				else schedule_effect(effect);
			}
		}
	}
	/**
	* @template T
	* @param {T} value
	* @returns {T}
	*/
	function proxy(value) {
		if (typeof value !== "object" || value === null || STATE_SYMBOL in value) return value;
		const prototype = get_prototype_of(value);
		if (prototype !== object_prototype && prototype !== array_prototype) return value;
		/** @type {Map<any, Source<any>>} */
		var sources = /* @__PURE__ */ new Map();
		var is_proxied_array = is_array(value);
		var version = /* @__PURE__ */ state(0);
		var stack = null;
		var parent_version = update_version;
		/**
		* Executes the proxy in the context of the reaction it was originally created in, if any
		* @template T
		* @param {() => T} fn
		*/
		var with_parent = (fn) => {
			if (update_version === parent_version) return fn();
			var reaction = active_reaction;
			var version = update_version;
			set_active_reaction(null);
			set_update_version(parent_version);
			var result = fn();
			set_active_reaction(reaction);
			set_update_version(version);
			return result;
		};
		if (is_proxied_array) sources.set("length", /* @__PURE__ */ state(
			/** @type {any[]} */
			value.length,
			stack
		));
		return new Proxy(value, {
			defineProperty(_, prop, descriptor) {
				if (!("value" in descriptor) || descriptor.configurable === false || descriptor.enumerable === false || descriptor.writable === false) state_descriptors_fixed();
				var s = sources.get(prop);
				if (s === void 0) with_parent(() => {
					var s = /* @__PURE__ */ state(descriptor.value, stack);
					sources.set(prop, s);
					return s;
				});
				else set(s, descriptor.value, true);
				return true;
			},
			deleteProperty(target, prop) {
				var s = sources.get(prop);
				if (s === void 0) {
					if (prop in target) {
						const s = with_parent(() => /* @__PURE__ */ state(UNINITIALIZED, stack));
						sources.set(prop, s);
						increment(version);
					}
				} else {
					set(s, UNINITIALIZED);
					increment(version);
				}
				return true;
			},
			get(target, prop, receiver) {
				if (prop === STATE_SYMBOL) return value;
				var s = sources.get(prop);
				var exists = prop in target;
				if (s === void 0 && (!exists || get_descriptor(target, prop)?.writable)) {
					s = with_parent(() => {
						return /* @__PURE__ */ state(proxy(exists ? target[prop] : UNINITIALIZED), stack);
					});
					sources.set(prop, s);
				}
				if (s !== void 0) {
					var v = get(s);
					return v === UNINITIALIZED ? void 0 : v;
				}
				return Reflect.get(target, prop, receiver);
			},
			getOwnPropertyDescriptor(target, prop) {
				var descriptor = Reflect.getOwnPropertyDescriptor(target, prop);
				if (descriptor && "value" in descriptor) {
					var s = sources.get(prop);
					if (s) descriptor.value = get(s);
				} else if (descriptor === void 0) {
					var source = sources.get(prop);
					var value = source?.v;
					if (source !== void 0 && value !== UNINITIALIZED) return {
						enumerable: true,
						configurable: true,
						value,
						writable: true
					};
				}
				return descriptor;
			},
			has(target, prop) {
				if (prop === STATE_SYMBOL) return true;
				var s = sources.get(prop);
				var has = s !== void 0 && s.v !== UNINITIALIZED || Reflect.has(target, prop);
				if (s !== void 0 || active_effect !== null && (!has || get_descriptor(target, prop)?.writable)) {
					if (s === void 0) {
						s = with_parent(() => {
							return /* @__PURE__ */ state(has ? proxy(target[prop]) : UNINITIALIZED, stack);
						});
						sources.set(prop, s);
					}
					if (get(s) === UNINITIALIZED) return false;
				}
				return has;
			},
			set(target, prop, value, receiver) {
				var s = sources.get(prop);
				var has = prop in target;
				if (is_proxied_array && prop === "length") for (var i = value; i < s.v; i += 1) {
					var other_s = sources.get(i + "");
					if (other_s !== void 0) set(other_s, UNINITIALIZED);
					else if (i in target) {
						other_s = with_parent(() => /* @__PURE__ */ state(UNINITIALIZED, stack));
						sources.set(i + "", other_s);
					}
				}
				if (s === void 0) {
					if (!has || get_descriptor(target, prop)?.writable) {
						s = with_parent(() => /* @__PURE__ */ state(void 0, stack));
						set(s, proxy(value));
						sources.set(prop, s);
					}
				} else {
					has = s.v !== UNINITIALIZED;
					var p = with_parent(() => proxy(value));
					set(s, p);
				}
				var descriptor = Reflect.getOwnPropertyDescriptor(target, prop);
				if (descriptor?.set) descriptor.set.call(receiver, value);
				if (!has) {
					if (is_proxied_array && typeof prop === "string") {
						var ls = sources.get("length");
						var n = Number(prop);
						if (Number.isInteger(n) && n >= ls.v) set(ls, n + 1);
					}
					increment(version);
				}
				return true;
			},
			ownKeys(target) {
				get(version);
				var own_keys = Reflect.ownKeys(target).filter((key) => {
					var source = sources.get(key);
					return source === void 0 || source.v !== UNINITIALIZED;
				});
				for (var [key, source] of sources) if (source.v !== UNINITIALIZED && !(key in target)) own_keys.push(key);
				return own_keys;
			},
			setPrototypeOf() {
				state_prototype_fixed();
			}
		});
	}
	/**
	* @param {any} value
	*/
	function get_proxied_value(value) {
		try {
			if (value !== null && typeof value === "object" && STATE_SYMBOL in value) return value[STATE_SYMBOL];
		} catch {}
		return value;
	}
	/**
	* @param {any} a
	* @param {any} b
	*/
	function is(a, b) {
		return Object.is(get_proxied_value(a), get_proxied_value(b));
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/dom/operations.js
	/** @import { Effect, TemplateNode } from '#client' */
	/** @type {Window} */
	var $window;
	/** @type {Document} */
	var $document;
	/** @type {boolean} */
	var is_firefox;
	/** @type {() => Node | null} */
	var first_child_getter;
	/** @type {() => Node | null} */
	var next_sibling_getter;
	/**
	* Initialize these lazily to avoid issues when using the runtime in a server context
	* where these globals are not available while avoiding a separate server entry point
	*/
	function init_operations() {
		if ($window !== void 0) return;
		$window = window;
		$document = document;
		is_firefox = /Firefox/.test(navigator.userAgent);
		var element_prototype = Element.prototype;
		var node_prototype = Node.prototype;
		var text_prototype = Text.prototype;
		first_child_getter = get_descriptor(node_prototype, "firstChild").get;
		next_sibling_getter = get_descriptor(node_prototype, "nextSibling").get;
		if (is_extensible(element_prototype)) {
			element_prototype.__click = void 0;
			element_prototype.__className = void 0;
			element_prototype.__attributes = null;
			element_prototype.__style = void 0;
			element_prototype.__e = void 0;
		}
		if (is_extensible(text_prototype)) text_prototype.__t = void 0;
	}
	/**
	* @param {string} value
	* @returns {Text}
	*/
	function create_text(value = "") {
		return document.createTextNode(value);
	}
	/**
	* @template {Node} N
	* @param {N} node
	*/
	/* @__NO_SIDE_EFFECTS__ */
	function get_first_child(node) {
		return first_child_getter.call(node);
	}
	/**
	* @template {Node} N
	* @param {N} node
	*/
	/* @__NO_SIDE_EFFECTS__ */
	function get_next_sibling(node) {
		return next_sibling_getter.call(node);
	}
	/**
	* Don't mark this as side-effect-free, hydration needs to walk all nodes
	* @template {Node} N
	* @param {N} node
	* @param {boolean} is_text
	* @returns {TemplateNode | null}
	*/
	function child(node, is_text) {
		if (!hydrating) return /* @__PURE__ */ get_first_child(node);
		var child = /* @__PURE__ */ get_first_child(hydrate_node);
		if (child === null) child = hydrate_node.appendChild(create_text());
		else if (is_text && child.nodeType !== 3) {
			var text = create_text();
			child?.before(text);
			set_hydrate_node(text);
			return text;
		}
		if (is_text) merge_text_nodes(child);
		set_hydrate_node(child);
		return child;
	}
	/**
	* Don't mark this as side-effect-free, hydration needs to walk all nodes
	* @param {TemplateNode} node
	* @param {boolean} [is_text]
	* @returns {TemplateNode | null}
	*/
	function first_child(node, is_text = false) {
		if (!hydrating) {
			var first = /* @__PURE__ */ get_first_child(node);
			if (first instanceof Comment && first.data === "") return /* @__PURE__ */ get_next_sibling(first);
			return first;
		}
		if (is_text) {
			if (hydrate_node?.nodeType !== 3) {
				var text = create_text();
				hydrate_node?.before(text);
				set_hydrate_node(text);
				return text;
			}
			merge_text_nodes(hydrate_node);
		}
		return hydrate_node;
	}
	/**
	* Don't mark this as side-effect-free, hydration needs to walk all nodes
	* @param {TemplateNode} node
	* @param {number} count
	* @param {boolean} is_text
	* @returns {TemplateNode | null}
	*/
	function sibling(node, count = 1, is_text = false) {
		let next_sibling = hydrating ? hydrate_node : node;
		var last_sibling;
		while (count--) {
			last_sibling = next_sibling;
			next_sibling = /* @__PURE__ */ get_next_sibling(next_sibling);
		}
		if (!hydrating) return next_sibling;
		if (is_text) {
			if (next_sibling?.nodeType !== 3) {
				var text = create_text();
				if (next_sibling === null) last_sibling?.after(text);
				else next_sibling.before(text);
				set_hydrate_node(text);
				return text;
			}
			merge_text_nodes(next_sibling);
		}
		set_hydrate_node(next_sibling);
		return next_sibling;
	}
	/**
	* @template {Node} N
	* @param {N} node
	* @returns {void}
	*/
	function clear_text_content(node) {
		node.textContent = "";
	}
	/**
	* Returns `true` if we're updating the current block, for example `condition` in
	* an `{#if condition}` block just changed. In this case, the branch should be
	* appended (or removed) at the same time as other updates within the
	* current `<svelte:boundary>`
	*/
	function should_defer_append() {
		if (!async_mode_flag) return false;
		if (eager_block_effects !== null) return false;
		return (active_effect.f & REACTION_RAN) !== 0;
	}
	/**
	* @template {keyof HTMLElementTagNameMap | string} T
	* @param {T} tag
	* @param {string} [namespace]
	* @param {string} [is]
	* @returns {T extends keyof HTMLElementTagNameMap ? HTMLElementTagNameMap[T] : Element}
	*/
	function create_element(tag, namespace, is) {
		let options = is ? { is } : void 0;
		return document.createElementNS(namespace ?? "http://www.w3.org/1999/xhtml", tag, options);
	}
	/**
	* Browsers split text nodes larger than 65536 bytes when parsing.
	* For hydration to succeed, we need to stitch them back together
	* @param {Text} text
	*/
	function merge_text_nodes(text) {
		if (text.nodeValue.length < 65536) return;
		let next = text.nextSibling;
		while (next !== null && next.nodeType === 3) {
			next.remove();
			/** @type {string} */ text.nodeValue += next.nodeValue;
			next = text.nextSibling;
		}
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/dom/elements/misc.js
	/**
	* @param {HTMLElement} dom
	* @param {boolean} value
	* @returns {void}
	*/
	function autofocus(dom, value) {
		if (value) {
			const body = document.body;
			dom.autofocus = true;
			queue_micro_task(() => {
				if (document.activeElement === body) dom.focus();
			});
		}
	}
	var listening_to_form_reset = false;
	function add_form_reset_listener() {
		if (!listening_to_form_reset) {
			listening_to_form_reset = true;
			document.addEventListener("reset", (evt) => {
				Promise.resolve().then(() => {
					if (!evt.defaultPrevented) for (const e of evt.target.elements) e.__on_r?.();
				});
			}, { capture: true });
		}
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/dom/elements/bindings/shared.js
	/**
	* @template T
	* @param {() => T} fn
	*/
	function without_reactive_context(fn) {
		var previous_reaction = active_reaction;
		var previous_effect = active_effect;
		set_active_reaction(null);
		set_active_effect(null);
		try {
			return fn();
		} finally {
			set_active_reaction(previous_reaction);
			set_active_effect(previous_effect);
		}
	}
	/**
	* Listen to the given event, and then instantiate a global form reset listener if not already done,
	* to notify all bindings when the form is reset
	* @param {HTMLElement} element
	* @param {string} event
	* @param {(is_reset?: true) => void} handler
	* @param {(is_reset?: true) => void} [on_reset]
	*/
	function listen_to_event_and_reset_event(element, event, handler, on_reset = handler) {
		element.addEventListener(event, () => without_reactive_context(handler));
		const prev = element.__on_r;
		if (prev) element.__on_r = () => {
			prev();
			on_reset(true);
		};
		else element.__on_r = () => on_reset(true);
		add_form_reset_listener();
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/reactivity/effects.js
	/** @import { Blocker, ComponentContext, ComponentContextLegacy, Derived, Effect, TemplateNode, TransitionManager } from '#client' */
	/**
	* @param {'$effect' | '$effect.pre' | '$inspect'} rune
	*/
	function validate_effect(rune) {
		if (active_effect === null) {
			if (active_reaction === null) effect_orphan(rune);
			effect_in_unowned_derived();
		}
		if (is_destroying_effect) effect_in_teardown(rune);
	}
	/**
	* @param {Effect} effect
	* @param {Effect} parent_effect
	*/
	function push_effect(effect, parent_effect) {
		var parent_last = parent_effect.last;
		if (parent_last === null) parent_effect.last = parent_effect.first = effect;
		else {
			parent_last.next = effect;
			effect.prev = parent_last;
			parent_effect.last = effect;
		}
	}
	/**
	* @param {number} type
	* @param {null | (() => void | (() => void))} fn
	* @returns {Effect}
	*/
	function create_effect(type, fn) {
		var parent = active_effect;
		if (parent !== null && (parent.f & 8192) !== 0) type |= INERT;
		/** @type {Effect} */
		var effect = {
			ctx: component_context,
			deps: null,
			nodes: null,
			f: type | DIRTY | 512,
			first: null,
			fn,
			last: null,
			next: null,
			parent,
			b: parent && parent.b,
			prev: null,
			teardown: null,
			wv: 0,
			ac: null
		};
		current_batch?.register_created_effect(effect);
		/** @type {Effect | null} */
		var e = effect;
		if ((type & 4) !== 0) if (collected_effects !== null) collected_effects.push(effect);
		else Batch.ensure().schedule(effect);
		else if (fn !== null) {
			try {
				update_effect(effect);
			} catch (e) {
				destroy_effect(effect);
				throw e;
			}
			if (e.deps === null && e.teardown === null && e.nodes === null && e.first === e.last && (e.f & 524288) === 0) {
				e = e.first;
				if ((type & 16) !== 0 && (type & 65536) !== 0 && e !== null) e.f |= EFFECT_TRANSPARENT;
			}
		}
		if (e !== null) {
			e.parent = parent;
			if (parent !== null) push_effect(e, parent);
			if (active_reaction !== null && (active_reaction.f & 2) !== 0 && (type & 64) === 0) {
				var derived = active_reaction;
				(derived.effects ??= []).push(e);
			}
		}
		return effect;
	}
	/**
	* Internal representation of `$effect.tracking()`
	* @returns {boolean}
	*/
	function effect_tracking() {
		return active_reaction !== null && !untracking;
	}
	/**
	* @param {() => void} fn
	*/
	function teardown(fn) {
		const effect = create_effect(8, null);
		set_signal_status(effect, CLEAN);
		effect.teardown = fn;
		return effect;
	}
	/**
	* Internal representation of `$effect(...)`
	* @param {() => void | (() => void)} fn
	*/
	function user_effect(fn) {
		validate_effect("$effect");
		var flags = active_effect.f;
		if (!active_reaction && (flags & 32) !== 0 && (flags & 32768) === 0) {
			var context = component_context;
			(context.e ??= []).push(fn);
		} else return create_user_effect(fn);
	}
	/**
	* @param {() => void | (() => void)} fn
	*/
	function create_user_effect(fn) {
		return create_effect(4 | USER_EFFECT, fn);
	}
	/**
	* Internal representation of `$effect.pre(...)`
	* @param {() => void | (() => void)} fn
	* @returns {Effect}
	*/
	function user_pre_effect(fn) {
		validate_effect("$effect.pre");
		return create_effect(8 | USER_EFFECT, fn);
	}
	/**
	* An effect root whose children can transition out
	* @param {() => void} fn
	* @returns {(options?: { outro?: boolean }) => Promise<void>}
	*/
	function component_root(fn) {
		Batch.ensure();
		const effect = create_effect(64 | EFFECT_PRESERVED, fn);
		return (options = {}) => {
			return new Promise((fulfil) => {
				if (options.outro) pause_effect(effect, () => {
					destroy_effect(effect);
					fulfil(void 0);
				});
				else {
					destroy_effect(effect);
					fulfil(void 0);
				}
			});
		};
	}
	/**
	* @param {() => void | (() => void)} fn
	* @returns {Effect}
	*/
	function effect(fn) {
		return create_effect(4, fn);
	}
	/**
	* Internal representation of `$: ..`
	* @param {() => any} deps
	* @param {() => void | (() => void)} fn
	*/
	function legacy_pre_effect(deps, fn) {
		var context = component_context;
		/** @type {{ effect: null | Effect, ran: boolean, deps: () => any }} */
		var token = {
			effect: null,
			ran: false,
			deps
		};
		context.l.$.push(token);
		token.effect = render_effect(() => {
			deps();
			if (token.ran) return;
			token.ran = true;
			var effect = active_effect;
			try {
				set_active_effect(effect.parent);
				untrack(fn);
			} finally {
				set_active_effect(effect);
			}
		});
	}
	function legacy_pre_effect_reset() {
		var context = component_context;
		render_effect(() => {
			for (var token of context.l.$) {
				token.deps();
				var effect = token.effect;
				if ((effect.f & 1024) !== 0 && effect.deps !== null) set_signal_status(effect, MAYBE_DIRTY);
				if (is_dirty(effect)) update_effect(effect);
				token.ran = false;
			}
		});
	}
	/**
	* @param {() => void | (() => void)} fn
	* @returns {Effect}
	*/
	function async_effect(fn) {
		return create_effect(ASYNC | EFFECT_PRESERVED, fn);
	}
	/**
	* @param {() => void | (() => void)} fn
	* @returns {Effect}
	*/
	function render_effect(fn, flags = 0) {
		return create_effect(8 | flags, fn);
	}
	/**
	* @param {(...expressions: any) => void | (() => void)} fn
	* @param {Array<() => any>} sync
	* @param {Array<() => Promise<any>>} async
	* @param {Blocker[]} blockers
	*/
	function template_effect(fn, sync = [], async = [], blockers = []) {
		flatten(blockers, sync, async, (values) => {
			create_effect(8, () => fn(...values.map(get)));
		});
	}
	/**
	* Like `template_effect`, but with an effect which is deferred until the batch commits
	* @param {(...expressions: any) => void | (() => void)} fn
	* @param {Array<() => any>} sync
	* @param {Array<() => Promise<any>>} async
	* @param {Blocker[]} blockers
	*/
	function deferred_template_effect(fn, sync = [], async = [], blockers = []) {
		if (async.length > 0 || blockers.length > 0) var decrement_pending = increment_pending();
		flatten(blockers, sync, async, (values) => {
			create_effect(4, () => fn(...values.map(get)));
			if (decrement_pending) decrement_pending();
		});
	}
	/**
	* @param {(() => void)} fn
	* @param {number} flags
	*/
	function block(fn, flags = 0) {
		return create_effect(16 | flags, fn);
	}
	/**
	* @param {(() => void)} fn
	* @param {number} flags
	*/
	function managed(fn, flags = 0) {
		return create_effect(MANAGED_EFFECT | flags, fn);
	}
	/**
	* @param {(() => void)} fn
	*/
	function branch(fn) {
		return create_effect(32 | EFFECT_PRESERVED, fn);
	}
	/**
	* @param {Effect} effect
	*/
	function execute_effect_teardown(effect) {
		var teardown = effect.teardown;
		if (teardown !== null) {
			const previously_destroying_effect = is_destroying_effect;
			const previous_reaction = active_reaction;
			set_is_destroying_effect(true);
			set_active_reaction(null);
			try {
				teardown.call(null);
			} finally {
				set_is_destroying_effect(previously_destroying_effect);
				set_active_reaction(previous_reaction);
			}
		}
	}
	/**
	* @param {Effect} signal
	* @param {boolean} remove_dom
	* @returns {void}
	*/
	function destroy_effect_children(signal, remove_dom = false) {
		var effect = signal.first;
		signal.first = signal.last = null;
		while (effect !== null) {
			const controller = effect.ac;
			if (controller !== null) without_reactive_context(() => {
				controller.abort(STALE_REACTION);
			});
			var next = effect.next;
			if ((effect.f & 64) !== 0) effect.parent = null;
			else destroy_effect(effect, remove_dom);
			effect = next;
		}
	}
	/**
	* @param {Effect} signal
	* @returns {void}
	*/
	function destroy_block_effect_children(signal) {
		var effect = signal.first;
		while (effect !== null) {
			var next = effect.next;
			if ((effect.f & 32) === 0) destroy_effect(effect);
			effect = next;
		}
	}
	/**
	* @param {Effect} effect
	* @param {boolean} [remove_dom]
	* @returns {void}
	*/
	function destroy_effect(effect, remove_dom = true) {
		var removed = false;
		if ((remove_dom || (effect.f & 262144) !== 0) && effect.nodes !== null && effect.nodes.end !== null) {
			remove_effect_dom(effect.nodes.start, effect.nodes.end);
			removed = true;
		}
		set_signal_status(effect, DESTROYING);
		destroy_effect_children(effect, remove_dom && !removed);
		remove_reactions(effect, 0);
		var transitions = effect.nodes && effect.nodes.t;
		if (transitions !== null) for (const transition of transitions) transition.stop();
		execute_effect_teardown(effect);
		effect.f ^= DESTROYING;
		effect.f |= DESTROYED;
		var parent = effect.parent;
		if (parent !== null && parent.first !== null) unlink_effect(effect);
		effect.next = effect.prev = effect.teardown = effect.ctx = effect.deps = effect.fn = effect.nodes = effect.ac = effect.b = null;
	}
	/**
	*
	* @param {TemplateNode | null} node
	* @param {TemplateNode} end
	*/
	function remove_effect_dom(node, end) {
		while (node !== null) {
			/** @type {TemplateNode | null} */
			var next = node === end ? null : /* @__PURE__ */ get_next_sibling(node);
			node.remove();
			node = next;
		}
	}
	/**
	* Detach an effect from the effect tree, freeing up memory and
	* reducing the amount of work that happens on subsequent traversals
	* @param {Effect} effect
	*/
	function unlink_effect(effect) {
		var parent = effect.parent;
		var prev = effect.prev;
		var next = effect.next;
		if (prev !== null) prev.next = next;
		if (next !== null) next.prev = prev;
		if (parent !== null) {
			if (parent.first === effect) parent.first = next;
			if (parent.last === effect) parent.last = prev;
		}
	}
	/**
	* When a block effect is removed, we don't immediately destroy it or yank it
	* out of the DOM, because it might have transitions. Instead, we 'pause' it.
	* It stays around (in memory, and in the DOM) until outro transitions have
	* completed, and if the state change is reversed then we _resume_ it.
	* A paused effect does not update, and the DOM subtree becomes inert.
	* @param {Effect} effect
	* @param {() => void} [callback]
	* @param {boolean} [destroy]
	*/
	function pause_effect(effect, callback, destroy = true) {
		/** @type {TransitionManager[]} */
		var transitions = [];
		pause_children(effect, transitions, true);
		var fn = () => {
			if (destroy) destroy_effect(effect);
			if (callback) callback();
		};
		var remaining = transitions.length;
		if (remaining > 0) {
			var check = () => --remaining || fn();
			for (var transition of transitions) transition.out(check);
		} else fn();
	}
	/**
	* @param {Effect} effect
	* @param {TransitionManager[]} transitions
	* @param {boolean} local
	*/
	function pause_children(effect, transitions, local) {
		if ((effect.f & 8192) !== 0) return;
		effect.f ^= INERT;
		var t = effect.nodes && effect.nodes.t;
		if (t !== null) {
			for (const transition of t) if (transition.is_global || local) transitions.push(transition);
		}
		var child = effect.first;
		while (child !== null) {
			var sibling = child.next;
			if ((child.f & 64) === 0) {
				var transparent = (child.f & 65536) !== 0 || (child.f & 32) !== 0 && (effect.f & 16) !== 0;
				pause_children(child, transitions, transparent ? local : false);
			}
			child = sibling;
		}
	}
	/**
	* The opposite of `pause_effect`. We call this if (for example)
	* `x` becomes falsy then truthy: `{#if x}...{/if}`
	* @param {Effect} effect
	*/
	function resume_effect(effect) {
		resume_children(effect, true);
	}
	/**
	* @param {Effect} effect
	* @param {boolean} local
	*/
	function resume_children(effect, local) {
		if ((effect.f & 8192) === 0) return;
		effect.f ^= INERT;
		if ((effect.f & 1024) === 0) {
			set_signal_status(effect, DIRTY);
			Batch.ensure().schedule(effect);
		}
		var child = effect.first;
		while (child !== null) {
			var sibling = child.next;
			var transparent = (child.f & 65536) !== 0 || (child.f & 32) !== 0;
			resume_children(child, transparent ? local : false);
			child = sibling;
		}
		var t = effect.nodes && effect.nodes.t;
		if (t !== null) {
			for (const transition of t) if (transition.is_global || local) transition.in();
		}
	}
	/**
	* @param {Effect} effect
	* @param {DocumentFragment} fragment
	*/
	function move_effect(effect, fragment) {
		if (!effect.nodes) return;
		/** @type {TemplateNode | null} */
		var node = effect.nodes.start;
		var end = effect.nodes.end;
		while (node !== null) {
			/** @type {TemplateNode | null} */
			var next = node === end ? null : /* @__PURE__ */ get_next_sibling(node);
			fragment.append(node);
			node = next;
		}
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/legacy.js
	/**
	* @type {Set<Value> | null}
	* @deprecated
	*/
	var captured_signals = null;
	//#endregion
	//#region node_modules/svelte/src/internal/client/runtime.js
	/** @import { Derived, Effect, Reaction, Source, Value } from '#client' */
	var is_updating_effect = false;
	var is_destroying_effect = false;
	/** @param {boolean} value */
	function set_is_destroying_effect(value) {
		is_destroying_effect = value;
	}
	/** @type {null | Reaction} */
	var active_reaction = null;
	var untracking = false;
	/** @param {null | Reaction} reaction */
	function set_active_reaction(reaction) {
		active_reaction = reaction;
	}
	/** @type {null | Effect} */
	var active_effect = null;
	/** @param {null | Effect} effect */
	function set_active_effect(effect) {
		active_effect = effect;
	}
	/**
	* When sources are created within a reaction, reading and writing
	* them within that reaction should not cause a re-run
	* @type {null | Source[]}
	*/
	var current_sources = null;
	/** @param {Value} value */
	function push_reaction_value(value) {
		if (active_reaction !== null && (!async_mode_flag || (active_reaction.f & 2) !== 0)) if (current_sources === null) current_sources = [value];
		else current_sources.push(value);
	}
	/**
	* The dependencies of the reaction that is currently being executed. In many cases,
	* the dependencies are unchanged between runs, and so this will be `null` unless
	* and until a new dependency is accessed — we track this via `skipped_deps`
	* @type {null | Value[]}
	*/
	var new_deps = null;
	var skipped_deps = 0;
	/**
	* Tracks writes that the effect it's executed in doesn't listen to yet,
	* so that the dependency can be added to the effect later on if it then reads it
	* @type {null | Source[]}
	*/
	var untracked_writes = null;
	/** @param {null | Source[]} value */
	function set_untracked_writes(value) {
		untracked_writes = value;
	}
	/**
	* @type {number} Used by sources and deriveds for handling updates.
	* Version starts from 1 so that unowned deriveds differentiate between a created effect and a run one for tracing
	**/
	var write_version = 1;
	/** @type {number} Used to version each read of a source of derived to avoid duplicating depedencies inside a reaction */
	var read_version = 0;
	var update_version = read_version;
	/** @param {number} value */
	function set_update_version(value) {
		update_version = value;
	}
	function increment_write_version() {
		return ++write_version;
	}
	/**
	* Determines whether a derived or effect is dirty.
	* If it is MAYBE_DIRTY, will set the status to CLEAN
	* @param {Reaction} reaction
	* @returns {boolean}
	*/
	function is_dirty(reaction) {
		var flags = reaction.f;
		if ((flags & 2048) !== 0) return true;
		if (flags & 2) reaction.f &= ~WAS_MARKED;
		if ((flags & 4096) !== 0) {
			var dependencies = reaction.deps;
			var length = dependencies.length;
			for (var i = 0; i < length; i++) {
				var dependency = dependencies[i];
				if (is_dirty(dependency)) update_derived(dependency);
				if (dependency.wv > reaction.wv) return true;
			}
			if ((flags & 512) !== 0 && batch_values === null) set_signal_status(reaction, CLEAN);
		}
		return false;
	}
	/**
	* @param {Value} signal
	* @param {Effect} effect
	* @param {boolean} [root]
	*/
	function schedule_possible_effect_self_invalidation(signal, effect, root = true) {
		var reactions = signal.reactions;
		if (reactions === null) return;
		if (!async_mode_flag && current_sources !== null && includes.call(current_sources, signal)) return;
		for (var i = 0; i < reactions.length; i++) {
			var reaction = reactions[i];
			if ((reaction.f & 2) !== 0) schedule_possible_effect_self_invalidation(reaction, effect, false);
			else if (effect === reaction) {
				if (root) set_signal_status(reaction, DIRTY);
				else if ((reaction.f & 1024) !== 0) set_signal_status(reaction, MAYBE_DIRTY);
				schedule_effect(reaction);
			}
		}
	}
	/** @param {Reaction} reaction */
	function update_reaction(reaction) {
		var previous_deps = new_deps;
		var previous_skipped_deps = skipped_deps;
		var previous_untracked_writes = untracked_writes;
		var previous_reaction = active_reaction;
		var previous_sources = current_sources;
		var previous_component_context = component_context;
		var previous_untracking = untracking;
		var previous_update_version = update_version;
		var flags = reaction.f;
		new_deps = null;
		skipped_deps = 0;
		untracked_writes = null;
		active_reaction = (flags & 96) === 0 ? reaction : null;
		current_sources = null;
		set_component_context(reaction.ctx);
		untracking = false;
		update_version = ++read_version;
		if (reaction.ac !== null) {
			without_reactive_context(() => {
				/** @type {AbortController} */ reaction.ac.abort(STALE_REACTION);
			});
			reaction.ac = null;
		}
		try {
			reaction.f |= REACTION_IS_UPDATING;
			var fn = reaction.fn;
			var result = fn();
			reaction.f |= REACTION_RAN;
			var deps = reaction.deps;
			var is_fork = current_batch?.is_fork;
			if (new_deps !== null) {
				var i;
				if (!is_fork) remove_reactions(reaction, skipped_deps);
				if (deps !== null && skipped_deps > 0) {
					deps.length = skipped_deps + new_deps.length;
					for (i = 0; i < new_deps.length; i++) deps[skipped_deps + i] = new_deps[i];
				} else reaction.deps = deps = new_deps;
				if (effect_tracking() && (reaction.f & 512) !== 0) for (i = skipped_deps; i < deps.length; i++) (deps[i].reactions ??= []).push(reaction);
			} else if (!is_fork && deps !== null && skipped_deps < deps.length) {
				remove_reactions(reaction, skipped_deps);
				deps.length = skipped_deps;
			}
			if (is_runes() && untracked_writes !== null && !untracking && deps !== null && (reaction.f & 6146) === 0) for (i = 0; i < untracked_writes.length; i++) schedule_possible_effect_self_invalidation(untracked_writes[i], reaction);
			if (previous_reaction !== null && previous_reaction !== reaction) {
				read_version++;
				if (previous_reaction.deps !== null) for (let i = 0; i < previous_skipped_deps; i += 1) previous_reaction.deps[i].rv = read_version;
				if (previous_deps !== null) for (const dep of previous_deps) dep.rv = read_version;
				if (untracked_writes !== null) if (previous_untracked_writes === null) previous_untracked_writes = untracked_writes;
				else previous_untracked_writes.push(...untracked_writes);
			}
			if ((reaction.f & 8388608) !== 0) reaction.f ^= ERROR_VALUE;
			return result;
		} catch (error) {
			return handle_error(error);
		} finally {
			reaction.f ^= REACTION_IS_UPDATING;
			new_deps = previous_deps;
			skipped_deps = previous_skipped_deps;
			untracked_writes = previous_untracked_writes;
			active_reaction = previous_reaction;
			current_sources = previous_sources;
			set_component_context(previous_component_context);
			untracking = previous_untracking;
			update_version = previous_update_version;
		}
	}
	/**
	* @template V
	* @param {Reaction} signal
	* @param {Value<V>} dependency
	* @returns {void}
	*/
	function remove_reaction(signal, dependency) {
		let reactions = dependency.reactions;
		if (reactions !== null) {
			var index = index_of.call(reactions, signal);
			if (index !== -1) {
				var new_length = reactions.length - 1;
				if (new_length === 0) reactions = dependency.reactions = null;
				else {
					reactions[index] = reactions[new_length];
					reactions.pop();
				}
			}
		}
		if (reactions === null && (dependency.f & 2) !== 0 && (new_deps === null || !includes.call(new_deps, dependency))) {
			var derived = dependency;
			if ((derived.f & 512) !== 0) {
				derived.f ^= 512;
				derived.f &= ~WAS_MARKED;
			}
			if (derived.v !== UNINITIALIZED) update_derived_status(derived);
			freeze_derived_effects(derived);
			remove_reactions(derived, 0);
		}
	}
	/**
	* @param {Reaction} signal
	* @param {number} start_index
	* @returns {void}
	*/
	function remove_reactions(signal, start_index) {
		var dependencies = signal.deps;
		if (dependencies === null) return;
		for (var i = start_index; i < dependencies.length; i++) remove_reaction(signal, dependencies[i]);
	}
	/**
	* @param {Effect} effect
	* @returns {void}
	*/
	function update_effect(effect) {
		var flags = effect.f;
		if ((flags & 16384) !== 0) return;
		set_signal_status(effect, CLEAN);
		var previous_effect = active_effect;
		var was_updating_effect = is_updating_effect;
		active_effect = effect;
		is_updating_effect = true;
		try {
			if ((flags & 16777232) !== 0) destroy_block_effect_children(effect);
			else destroy_effect_children(effect);
			execute_effect_teardown(effect);
			var teardown = update_reaction(effect);
			effect.teardown = typeof teardown === "function" ? teardown : null;
			effect.wv = write_version;
		} finally {
			is_updating_effect = was_updating_effect;
			active_effect = previous_effect;
		}
	}
	/**
	* Returns a promise that resolves once any pending state changes have been applied.
	* @returns {Promise<void>}
	*/
	async function tick() {
		if (async_mode_flag) return new Promise((f) => {
			requestAnimationFrame(() => f());
			setTimeout(() => f());
		});
		await Promise.resolve();
		flushSync();
	}
	/**
	* @template V
	* @param {Value<V>} signal
	* @returns {V}
	*/
	function get(signal) {
		var is_derived = (signal.f & 2) !== 0;
		captured_signals?.add(signal);
		if (active_reaction !== null && !untracking) {
			if (!(active_effect !== null && (active_effect.f & 16384) !== 0) && (current_sources === null || !includes.call(current_sources, signal))) {
				var deps = active_reaction.deps;
				if ((active_reaction.f & 2097152) !== 0) {
					if (signal.rv < read_version) {
						signal.rv = read_version;
						if (new_deps === null && deps !== null && deps[skipped_deps] === signal) skipped_deps++;
						else if (new_deps === null) new_deps = [signal];
						else new_deps.push(signal);
					}
				} else {
					(active_reaction.deps ??= []).push(signal);
					var reactions = signal.reactions;
					if (reactions === null) signal.reactions = [active_reaction];
					else if (!includes.call(reactions, active_reaction)) reactions.push(active_reaction);
				}
			}
		}
		if (is_destroying_effect && old_values.has(signal)) return old_values.get(signal);
		if (is_derived) {
			var derived = signal;
			if (is_destroying_effect) {
				var value = derived.v;
				if ((derived.f & 1024) === 0 && derived.reactions !== null || depends_on_old_values(derived)) value = execute_derived(derived);
				old_values.set(derived, value);
				return value;
			}
			var should_connect = (derived.f & 512) === 0 && !untracking && active_reaction !== null && (is_updating_effect || (active_reaction.f & 512) !== 0);
			var is_new = (derived.f & REACTION_RAN) === 0;
			if (is_dirty(derived)) {
				if (should_connect) derived.f |= 512;
				update_derived(derived);
			}
			if (should_connect && !is_new) {
				unfreeze_derived_effects(derived);
				reconnect(derived);
			}
		}
		if (batch_values?.has(signal)) return batch_values.get(signal);
		if ((signal.f & 8388608) !== 0) throw signal.v;
		return signal.v;
	}
	/**
	* (Re)connect a disconnected derived, so that it is notified
	* of changes in `mark_reactions`
	* @param {Derived} derived
	*/
	function reconnect(derived) {
		derived.f |= 512;
		if (derived.deps === null) return;
		for (const dep of derived.deps) {
			(dep.reactions ??= []).push(derived);
			if ((dep.f & 2) !== 0 && (dep.f & 512) === 0) {
				unfreeze_derived_effects(dep);
				reconnect(dep);
			}
		}
	}
	/** @param {Derived} derived */
	function depends_on_old_values(derived) {
		if (derived.v === UNINITIALIZED) return true;
		if (derived.deps === null) return false;
		for (const dep of derived.deps) {
			if (old_values.has(dep)) return true;
			if ((dep.f & 2) !== 0 && depends_on_old_values(dep)) return true;
		}
		return false;
	}
	/**
	* When used inside a [`$derived`](https://svelte.dev/docs/svelte/$derived) or [`$effect`](https://svelte.dev/docs/svelte/$effect),
	* any state read inside `fn` will not be treated as a dependency.
	*
	* ```ts
	* $effect(() => {
	*   // this will run when `data` changes, but not when `time` changes
	*   save(data, {
	*     timestamp: untrack(() => time)
	*   });
	* });
	* ```
	* @template T
	* @param {() => T} fn
	* @returns {T}
	*/
	function untrack(fn) {
		var previous_untracking = untracking;
		try {
			untracking = true;
			return fn();
		} finally {
			untracking = previous_untracking;
		}
	}
	/**
	* Possibly traverse an object and read all its properties so that they're all reactive in case this is `$state`.
	* Does only check first level of an object for performance reasons (heuristic should be good for 99% of all cases).
	* @param {any} value
	* @returns {void}
	*/
	function deep_read_state(value) {
		if (typeof value !== "object" || !value || value instanceof EventTarget) return;
		if (STATE_SYMBOL in value) deep_read(value);
		else if (!Array.isArray(value)) for (let key in value) {
			const prop = value[key];
			if (typeof prop === "object" && prop && STATE_SYMBOL in prop) deep_read(prop);
		}
	}
	/**
	* Deeply traverse an object and read all its properties
	* so that they're all reactive in case this is `$state`
	* @param {any} value
	* @param {Set<any>} visited
	* @returns {void}
	*/
	function deep_read(value, visited = /* @__PURE__ */ new Set()) {
		if (typeof value === "object" && value !== null && !(value instanceof EventTarget) && !visited.has(value)) {
			visited.add(value);
			if (value instanceof Date) value.getTime();
			for (let key in value) try {
				deep_read(value[key], visited);
			} catch (e) {}
			const proto = get_prototype_of(value);
			if (proto !== Object.prototype && proto !== Array.prototype && proto !== Map.prototype && proto !== Set.prototype && proto !== Date.prototype) {
				const descriptors = get_descriptors(proto);
				for (let key in descriptors) {
					const get = descriptors[key].get;
					if (get) try {
						get.call(value);
					} catch (e) {}
				}
			}
		}
	}
	//#endregion
	//#region node_modules/svelte/src/utils.js
	/**
	* @param {string} name
	*/
	function is_capture_event(name) {
		return name.endsWith("capture") && name !== "gotpointercapture" && name !== "lostpointercapture";
	}
	/** List of Element events that will be delegated */
	var DELEGATED_EVENTS = [
		"beforeinput",
		"click",
		"change",
		"dblclick",
		"contextmenu",
		"focusin",
		"focusout",
		"input",
		"keydown",
		"keyup",
		"mousedown",
		"mousemove",
		"mouseout",
		"mouseover",
		"mouseup",
		"pointerdown",
		"pointermove",
		"pointerout",
		"pointerover",
		"pointerup",
		"touchend",
		"touchmove",
		"touchstart"
	];
	/**
	* Returns `true` if `event_name` is a delegated event
	* @param {string} event_name
	*/
	function can_delegate_event(event_name) {
		return DELEGATED_EVENTS.includes(event_name);
	}
	/**
	* Attributes that are boolean, i.e. they are present or not present.
	*/
	var DOM_BOOLEAN_ATTRIBUTES = [
		"allowfullscreen",
		"async",
		"autofocus",
		"autoplay",
		"checked",
		"controls",
		"default",
		"disabled",
		"formnovalidate",
		"indeterminate",
		"inert",
		"ismap",
		"loop",
		"multiple",
		"muted",
		"nomodule",
		"novalidate",
		"open",
		"playsinline",
		"readonly",
		"required",
		"reversed",
		"seamless",
		"selected",
		"webkitdirectory",
		"defer",
		"disablepictureinpicture",
		"disableremoteplayback"
	];
	/**
	* @type {Record<string, string>}
	* List of attribute names that should be aliased to their property names
	* because they behave differently between setting them as an attribute and
	* setting them as a property.
	*/
	var ATTRIBUTE_ALIASES = {
		formnovalidate: "formNoValidate",
		ismap: "isMap",
		nomodule: "noModule",
		playsinline: "playsInline",
		readonly: "readOnly",
		defaultvalue: "defaultValue",
		defaultchecked: "defaultChecked",
		srcobject: "srcObject",
		novalidate: "noValidate",
		allowfullscreen: "allowFullscreen",
		disablepictureinpicture: "disablePictureInPicture",
		disableremoteplayback: "disableRemotePlayback"
	};
	/**
	* @param {string} name
	*/
	function normalize_attribute(name) {
		name = name.toLowerCase();
		return ATTRIBUTE_ALIASES[name] ?? name;
	}
	[...DOM_BOOLEAN_ATTRIBUTES];
	/**
	* Subset of delegated events which should be passive by default.
	* These two are already passive via browser defaults on window, document and body.
	* But since
	* - we're delegating them
	* - they happen often
	* - they apply to mobile which is generally less performant
	* we're marking them as passive by default for other elements, too.
	*/
	var PASSIVE_EVENTS = ["touchstart", "touchmove"];
	/**
	* Returns `true` if `name` is a passive event
	* @param {string} name
	*/
	function is_passive_event(name) {
		return PASSIVE_EVENTS.includes(name);
	}
	/** List of elements that require raw contents and should not have SSR comments put in them */
	var RAW_TEXT_ELEMENTS = [
		"textarea",
		"script",
		"style",
		"title"
	];
	/** @param {string} name */
	function is_raw_text_element(name) {
		return RAW_TEXT_ELEMENTS.includes(name);
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/dom/elements/events.js
	/**
	* Used on elements, as a map of event type -> event handler,
	* and on events themselves to track which element handled an event
	*/
	var event_symbol = Symbol("events");
	/** @type {Set<string>} */
	var all_registered_events = /* @__PURE__ */ new Set();
	/** @type {Set<(events: Array<string>) => void>} */
	var root_event_handles = /* @__PURE__ */ new Set();
	/**
	* @param {string} event_name
	* @param {EventTarget} dom
	* @param {EventListener} [handler]
	* @param {AddEventListenerOptions} [options]
	*/
	function create_event(event_name, dom, handler, options = {}) {
		/**
		* @this {EventTarget}
		*/
		function target_handler(event) {
			if (!options.capture) handle_event_propagation.call(dom, event);
			if (!event.cancelBubble) return without_reactive_context(() => {
				return handler?.call(this, event);
			});
		}
		if (event_name.startsWith("pointer") || event_name.startsWith("touch") || event_name === "wheel") queue_micro_task(() => {
			dom.addEventListener(event_name, target_handler, options);
		});
		else dom.addEventListener(event_name, target_handler, options);
		return target_handler;
	}
	/**
	* @param {string} event_name
	* @param {Element} dom
	* @param {EventListener} [handler]
	* @param {boolean} [capture]
	* @param {boolean} [passive]
	* @returns {void}
	*/
	function event(event_name, dom, handler, capture, passive) {
		var options = {
			capture,
			passive
		};
		var target_handler = create_event(event_name, dom, handler, options);
		if (dom === document.body || dom === window || dom === document || dom instanceof HTMLMediaElement) teardown(() => {
			dom.removeEventListener(event_name, target_handler, options);
		});
	}
	/**
	* @param {string} event_name
	* @param {Element} element
	* @param {EventListener} [handler]
	* @returns {void}
	*/
	function delegated(event_name, element, handler) {
		(element[event_symbol] ??= {})[event_name] = handler;
	}
	/**
	* @param {Array<string>} events
	* @returns {void}
	*/
	function delegate(events) {
		for (var i = 0; i < events.length; i++) all_registered_events.add(events[i]);
		for (var fn of root_event_handles) fn(events);
	}
	var last_propagated_event = null;
	/**
	* @this {EventTarget}
	* @param {Event} event
	* @returns {void}
	*/
	function handle_event_propagation(event) {
		var handler_element = this;
		var owner_document = handler_element.ownerDocument;
		var event_name = event.type;
		var path = event.composedPath?.() || [];
		var current_target = path[0] || event.target;
		last_propagated_event = event;
		var path_idx = 0;
		var handled_at = last_propagated_event === event && event[event_symbol];
		if (handled_at) {
			var at_idx = path.indexOf(handled_at);
			if (at_idx !== -1 && (handler_element === document || handler_element === window)) {
				event[event_symbol] = handler_element;
				return;
			}
			var handler_idx = path.indexOf(handler_element);
			if (handler_idx === -1) return;
			if (at_idx <= handler_idx) path_idx = at_idx;
		}
		current_target = path[path_idx] || event.target;
		if (current_target === handler_element) return;
		define_property(event, "currentTarget", {
			configurable: true,
			get() {
				return current_target || owner_document;
			}
		});
		var previous_reaction = active_reaction;
		var previous_effect = active_effect;
		set_active_reaction(null);
		set_active_effect(null);
		try {
			/**
			* @type {unknown}
			*/
			var throw_error;
			/**
			* @type {unknown[]}
			*/
			var other_errors = [];
			while (current_target !== null) {
				/** @type {null | Element} */
				var parent_element = current_target.assignedSlot || current_target.parentNode || current_target.host || null;
				try {
					var delegated = current_target[event_symbol]?.[event_name];
					if (delegated != null && (!current_target.disabled || event.target === current_target)) delegated.call(current_target, event);
				} catch (error) {
					if (throw_error) other_errors.push(error);
					else throw_error = error;
				}
				if (event.cancelBubble || parent_element === handler_element || parent_element === null) break;
				current_target = parent_element;
			}
			if (throw_error) {
				for (let error of other_errors) queueMicrotask(() => {
					throw error;
				});
				throw throw_error;
			}
		} finally {
			event[event_symbol] = handler_element;
			delete event.currentTarget;
			set_active_reaction(previous_reaction);
			set_active_effect(previous_effect);
		}
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/dom/reconciler.js
	var policy = globalThis?.window?.trustedTypes && /* @__PURE__ */ globalThis.window.trustedTypes.createPolicy("svelte-trusted-html", { 
	/** @param {string} html */
createHTML: (html) => {
		return html;
	} });
	/** @param {string} html */
	function create_trusted_html(html) {
		return policy?.createHTML(html) ?? html;
	}
	/**
	* @param {string} html
	*/
	function create_fragment_from_html(html) {
		var elem = create_element("template");
		elem.innerHTML = create_trusted_html(html.replaceAll("<!>", "<!---->"));
		return elem.content;
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/dom/template.js
	/** @import { Effect, EffectNodes, TemplateNode } from '#client' */
	/** @import { TemplateStructure } from './types' */
	/**
	* @param {TemplateNode} start
	* @param {TemplateNode | null} end
	*/
	function assign_nodes(start, end) {
		var effect = active_effect;
		if (effect.nodes === null) effect.nodes = {
			start,
			end,
			a: null,
			t: null
		};
	}
	/**
	* @param {string} content
	* @param {number} flags
	* @returns {() => Node | Node[]}
	*/
	/* @__NO_SIDE_EFFECTS__ */
	function from_html(content, flags) {
		var is_fragment = (flags & 1) !== 0;
		var use_import_node = (flags & 2) !== 0;
		/** @type {Node} */
		var node;
		/**
		* Whether or not the first item is a text/element node. If not, we need to
		* create an additional comment node to act as `effect.nodes.start`
		*/
		var has_start = !content.startsWith("<!>");
		return () => {
			if (hydrating) {
				assign_nodes(hydrate_node, null);
				return hydrate_node;
			}
			if (node === void 0) {
				node = create_fragment_from_html(has_start ? content : "<!>" + content);
				if (!is_fragment) node = /* @__PURE__ */ get_first_child(node);
			}
			var clone = use_import_node || is_firefox ? document.importNode(node, true) : node.cloneNode(true);
			if (is_fragment) {
				var start = /* @__PURE__ */ get_first_child(clone);
				var end = clone.lastChild;
				assign_nodes(start, end);
			} else assign_nodes(clone, clone);
			return clone;
		};
	}
	/**
	* @param {string} content
	* @param {number} flags
	* @param {'svg' | 'math'} ns
	* @returns {() => Node | Node[]}
	*/
	/* @__NO_SIDE_EFFECTS__ */
	function from_namespace(content, flags, ns = "svg") {
		/**
		* Whether or not the first item is a text/element node. If not, we need to
		* create an additional comment node to act as `effect.nodes.start`
		*/
		var has_start = !content.startsWith("<!>");
		var is_fragment = (flags & 1) !== 0;
		var wrapped = `<${ns}>${has_start ? content : "<!>" + content}</${ns}>`;
		/** @type {Element | DocumentFragment} */
		var node;
		return () => {
			if (hydrating) {
				assign_nodes(hydrate_node, null);
				return hydrate_node;
			}
			if (!node) {
				var root = /* @__PURE__ */ get_first_child(create_fragment_from_html(wrapped));
				if (is_fragment) {
					node = document.createDocumentFragment();
					while (/* @__PURE__ */ get_first_child(root)) node.appendChild(/* @__PURE__ */ get_first_child(root));
				} else node = /* @__PURE__ */ get_first_child(root);
			}
			var clone = node.cloneNode(true);
			if (is_fragment) {
				var start = /* @__PURE__ */ get_first_child(clone);
				var end = clone.lastChild;
				assign_nodes(start, end);
			} else assign_nodes(clone, clone);
			return clone;
		};
	}
	/**
	* @param {string} content
	* @param {number} flags
	*/
	/* @__NO_SIDE_EFFECTS__ */
	function from_svg(content, flags) {
		return /* @__PURE__ */ from_namespace(content, flags, "svg");
	}
	/**
	* Don't mark this as side-effect-free, hydration needs to walk all nodes
	* @param {any} value
	*/
	function text(value = "") {
		if (!hydrating) {
			var t = create_text(value + "");
			assign_nodes(t, t);
			return t;
		}
		var node = hydrate_node;
		if (node.nodeType !== 3) {
			node.before(node = create_text());
			set_hydrate_node(node);
		} else merge_text_nodes(node);
		assign_nodes(node, node);
		return node;
	}
	/**
	* @returns {TemplateNode | DocumentFragment}
	*/
	function comment() {
		if (hydrating) {
			assign_nodes(hydrate_node, null);
			return hydrate_node;
		}
		var frag = document.createDocumentFragment();
		var start = document.createComment("");
		var anchor = create_text();
		frag.append(start, anchor);
		assign_nodes(start, anchor);
		return frag;
	}
	/**
	* Assign the created (or in hydration mode, traversed) dom elements to the current block
	* and insert the elements into the dom (in client mode).
	* @param {Text | Comment | Element} anchor
	* @param {DocumentFragment | Element} dom
	*/
	function append(anchor, dom) {
		if (hydrating) {
			var effect = active_effect;
			if ((effect.f & 32768) === 0 || effect.nodes.end === null) effect.nodes.end = hydrate_node;
			hydrate_next();
			return;
		}
		if (anchor === null) return;
		anchor.before(dom);
	}
	/** @param {boolean} value */
	function set_should_intro(value) {}
	/**
	* @param {Element} text
	* @param {string} value
	* @returns {void}
	*/
	function set_text(text, value) {
		var str = value == null ? "" : typeof value === "object" ? `${value}` : value;
		if (str !== (text.__t ??= text.nodeValue)) {
			text.__t = str;
			text.nodeValue = `${str}`;
		}
	}
	/**
	* Mounts a component to the given target and returns the exports and potentially the props (if compiled with `accessors: true`) of the component.
	* Transitions will play during the initial render unless the `intro` option is set to `false`.
	*
	* @template {Record<string, any>} Props
	* @template {Record<string, any>} Exports
	* @param {ComponentType<SvelteComponent<Props>> | Component<Props, Exports, any>} component
	* @param {MountOptions<Props>} options
	* @returns {Exports}
	*/
	function mount(component, options) {
		return _mount(component, options);
	}
	/** @type {Map<EventTarget, Map<string, number>>} */
	var listeners = /* @__PURE__ */ new Map();
	/**
	* @template {Record<string, any>} Exports
	* @param {ComponentType<SvelteComponent<any>> | Component<any>} Component
	* @param {MountOptions} options
	* @returns {Exports}
	*/
	function _mount(Component, { target, anchor, props = {}, events, context, intro = true, transformError }) {
		init_operations();
		/** @type {Exports} */
		var component = void 0;
		var unmount = component_root(() => {
			var anchor_node = anchor ?? target.appendChild(create_text());
			boundary(anchor_node, { pending: () => {} }, (anchor_node) => {
				push({});
				var ctx = component_context;
				if (context) ctx.c = context;
				if (events)
 /** @type {any} */ props.$$events = events;
				if (hydrating) assign_nodes(anchor_node, null);
				component = Component(anchor_node, props) || {};
				if (hydrating) {
					/** @type {Effect & { nodes: EffectNodes }} */ active_effect.nodes.end = hydrate_node;
					if (hydrate_node === null || hydrate_node.nodeType !== 8 || hydrate_node.data !== "]") {
						hydration_mismatch();
						throw HYDRATION_ERROR;
					}
				}
				pop();
			}, transformError);
			/** @type {Set<string>} */
			var registered_events = /* @__PURE__ */ new Set();
			/** @param {Array<string>} events */
			var event_handle = (events) => {
				for (var i = 0; i < events.length; i++) {
					var event_name = events[i];
					if (registered_events.has(event_name)) continue;
					registered_events.add(event_name);
					var passive = is_passive_event(event_name);
					for (const node of [target, document]) {
						var counts = listeners.get(node);
						if (counts === void 0) {
							counts = /* @__PURE__ */ new Map();
							listeners.set(node, counts);
						}
						var count = counts.get(event_name);
						if (count === void 0) {
							node.addEventListener(event_name, handle_event_propagation, { passive });
							counts.set(event_name, 1);
						} else counts.set(event_name, count + 1);
					}
				}
			};
			event_handle(array_from(all_registered_events));
			root_event_handles.add(event_handle);
			return () => {
				for (var event_name of registered_events) for (const node of [target, document]) {
					var counts = listeners.get(node);
					var count = counts.get(event_name);
					if (--count == 0) {
						node.removeEventListener(event_name, handle_event_propagation);
						counts.delete(event_name);
						if (counts.size === 0) listeners.delete(node);
					} else counts.set(event_name, count);
				}
				root_event_handles.delete(event_handle);
				if (anchor_node !== anchor) anchor_node.parentNode?.removeChild(anchor_node);
			};
		});
		mounted_components.set(component, unmount);
		return component;
	}
	/**
	* References of the components that were mounted or hydrated.
	* Uses a `WeakMap` to avoid memory leaks.
	*/
	var mounted_components = /* @__PURE__ */ new WeakMap();
	//#endregion
	//#region node_modules/svelte/src/internal/client/dom/blocks/branches.js
	/** @import { Effect, TemplateNode } from '#client' */
	/**
	* @typedef {{ effect: Effect, fragment: DocumentFragment }} Branch
	*/
	/**
	* @template Key
	*/
	var BranchManager = class {
		/** @type {TemplateNode} */
		anchor;
		/** @type {Map<Batch, Key>} */
		#batches = /* @__PURE__ */ new Map();
		/**
		* Map of keys to effects that are currently rendered in the DOM.
		* These effects are visible and actively part of the document tree.
		* Example:
		* ```
		* {#if condition}
		* 	foo
		* {:else}
		* 	bar
		* {/if}
		* ```
		* Can result in the entries `true->Effect` and `false->Effect`
		* @type {Map<Key, Effect>}
		*/
		#onscreen = /* @__PURE__ */ new Map();
		/**
		* Similar to #onscreen with respect to the keys, but contains branches that are not yet
		* in the DOM, because their insertion is deferred.
		* @type {Map<Key, Branch>}
		*/
		#offscreen = /* @__PURE__ */ new Map();
		/**
		* Keys of effects that are currently outroing
		* @type {Set<Key>}
		*/
		#outroing = /* @__PURE__ */ new Set();
		/**
		* Whether to pause (i.e. outro) on change, or destroy immediately.
		* This is necessary for `<svelte:element>`
		*/
		#transition = true;
		/**
		* @param {TemplateNode} anchor
		* @param {boolean} transition
		*/
		constructor(anchor, transition = true) {
			this.anchor = anchor;
			this.#transition = transition;
		}
		/**
		* @param {Batch} batch
		*/
		#commit = (batch) => {
			if (!this.#batches.has(batch)) return;
			var key = this.#batches.get(batch);
			var onscreen = this.#onscreen.get(key);
			if (onscreen) {
				resume_effect(onscreen);
				this.#outroing.delete(key);
			} else {
				var offscreen = this.#offscreen.get(key);
				if (offscreen) {
					this.#onscreen.set(key, offscreen.effect);
					this.#offscreen.delete(key);
					/** @type {TemplateNode} */ offscreen.fragment.lastChild.remove();
					this.anchor.before(offscreen.fragment);
					onscreen = offscreen.effect;
				}
			}
			for (const [b, k] of this.#batches) {
				this.#batches.delete(b);
				if (b === batch) break;
				const offscreen = this.#offscreen.get(k);
				if (offscreen) {
					destroy_effect(offscreen.effect);
					this.#offscreen.delete(k);
				}
			}
			for (const [k, effect] of this.#onscreen) {
				if (k === key || this.#outroing.has(k)) continue;
				const on_destroy = () => {
					if (Array.from(this.#batches.values()).includes(k)) {
						var fragment = document.createDocumentFragment();
						move_effect(effect, fragment);
						fragment.append(create_text());
						this.#offscreen.set(k, {
							effect,
							fragment
						});
					} else destroy_effect(effect);
					this.#outroing.delete(k);
					this.#onscreen.delete(k);
				};
				if (this.#transition || !onscreen) {
					this.#outroing.add(k);
					pause_effect(effect, on_destroy, false);
				} else on_destroy();
			}
		};
		/**
		* @param {Batch} batch
		*/
		#discard = (batch) => {
			this.#batches.delete(batch);
			const keys = Array.from(this.#batches.values());
			for (const [k, branch] of this.#offscreen) if (!keys.includes(k)) {
				destroy_effect(branch.effect);
				this.#offscreen.delete(k);
			}
		};
		/**
		*
		* @param {any} key
		* @param {null | ((target: TemplateNode) => void)} fn
		*/
		ensure(key, fn) {
			var batch = current_batch;
			var defer = should_defer_append();
			if (fn && !this.#onscreen.has(key) && !this.#offscreen.has(key)) if (defer) {
				var fragment = document.createDocumentFragment();
				var target = create_text();
				fragment.append(target);
				this.#offscreen.set(key, {
					effect: branch(() => fn(target)),
					fragment
				});
			} else this.#onscreen.set(key, branch(() => fn(this.anchor)));
			this.#batches.set(batch, key);
			if (defer) {
				for (const [k, effect] of this.#onscreen) if (k === key) batch.unskip_effect(effect);
				else batch.skip_effect(effect);
				for (const [k, branch] of this.#offscreen) if (k === key) batch.unskip_effect(branch.effect);
				else batch.skip_effect(branch.effect);
				batch.oncommit(this.#commit);
				batch.ondiscard(this.#discard);
			} else {
				if (hydrating) this.anchor = hydrate_node;
				this.#commit(batch);
			}
		}
	};
	//#endregion
	//#region node_modules/svelte/src/internal/client/dom/blocks/if.js
	/** @import { TemplateNode } from '#client' */
	/**
	* @param {TemplateNode} node
	* @param {(branch: (fn: (anchor: Node) => void, key?: number | false) => void) => void} fn
	* @param {boolean} [elseif] True if this is an `{:else if ...}` block rather than an `{#if ...}`, as that affects which transitions are considered 'local'
	* @returns {void}
	*/
	function if_block(node, fn, elseif = false) {
		/** @type {TemplateNode | undefined} */
		var marker;
		if (hydrating) {
			marker = hydrate_node;
			hydrate_next();
		}
		var branches = new BranchManager(node);
		var flags = elseif ? EFFECT_TRANSPARENT : 0;
		/**
		* @param {number | false} key
		* @param {null | ((anchor: Node) => void)} fn
		*/
		function update_branch(key, fn) {
			if (hydrating) {
				var data = read_hydration_instruction(marker);
				if (key !== parseInt(data.substring(1))) {
					var anchor = skip_nodes();
					set_hydrate_node(anchor);
					branches.anchor = anchor;
					set_hydrating(false);
					branches.ensure(key, fn);
					set_hydrating(true);
					return;
				}
			}
			branches.ensure(key, fn);
		}
		block(() => {
			var has_branch = false;
			fn((fn, key = 0) => {
				has_branch = true;
				update_branch(key, fn);
			});
			if (!has_branch) update_branch(-1, null);
		}, flags);
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/dom/blocks/each.js
	/** @import { EachItem, EachOutroGroup, EachState, Effect, EffectNodes, MaybeSource, Source, TemplateNode, TransitionManager, Value } from '#client' */
	/** @import { Batch } from '../../reactivity/batch.js'; */
	/**
	* @param {any} _
	* @param {number} i
	*/
	function index(_, i) {
		return i;
	}
	/**
	* Pause multiple effects simultaneously, and coordinate their
	* subsequent destruction. Used in each blocks
	* @param {EachState} state
	* @param {Effect[]} to_destroy
	* @param {null | Node} controlled_anchor
	*/
	function pause_effects(state, to_destroy, controlled_anchor) {
		/** @type {TransitionManager[]} */
		var transitions = [];
		var length = to_destroy.length;
		/** @type {EachOutroGroup} */
		var group;
		var remaining = to_destroy.length;
		for (var i = 0; i < length; i++) {
			let effect = to_destroy[i];
			pause_effect(effect, () => {
				if (group) {
					group.pending.delete(effect);
					group.done.add(effect);
					if (group.pending.size === 0) {
						var groups = state.outrogroups;
						destroy_effects(state, array_from(group.done));
						groups.delete(group);
						if (groups.size === 0) state.outrogroups = null;
					}
				} else remaining -= 1;
			}, false);
		}
		if (remaining === 0) {
			var fast_path = transitions.length === 0 && controlled_anchor !== null;
			if (fast_path) {
				var anchor = controlled_anchor;
				var parent_node = anchor.parentNode;
				clear_text_content(parent_node);
				parent_node.append(anchor);
				state.items.clear();
			}
			destroy_effects(state, to_destroy, !fast_path);
		} else {
			group = {
				pending: new Set(to_destroy),
				done: /* @__PURE__ */ new Set()
			};
			(state.outrogroups ??= /* @__PURE__ */ new Set()).add(group);
		}
	}
	/**
	* @param {EachState} state
	* @param {Effect[]} to_destroy
	* @param {boolean} remove_dom
	*/
	function destroy_effects(state, to_destroy, remove_dom = true) {
		/** @type {Set<Effect> | undefined} */
		var preserved_effects;
		if (state.pending.size > 0) {
			preserved_effects = /* @__PURE__ */ new Set();
			for (const keys of state.pending.values()) for (const key of keys) preserved_effects.add(
				/** @type {EachItem} */
				state.items.get(key).e
			);
		}
		for (var i = 0; i < to_destroy.length; i++) {
			var e = to_destroy[i];
			if (preserved_effects?.has(e)) {
				e.f |= EFFECT_OFFSCREEN;
				move_effect(e, document.createDocumentFragment());
			} else destroy_effect(to_destroy[i], remove_dom);
		}
	}
	/** @type {TemplateNode} */
	var offscreen_anchor;
	/**
	* @template V
	* @param {Element | Comment} node The next sibling node, or the parent node if this is a 'controlled' block
	* @param {number} flags
	* @param {() => V[]} get_collection
	* @param {(value: V, index: number) => any} get_key
	* @param {(anchor: Node, item: MaybeSource<V>, index: MaybeSource<number>) => void} render_fn
	* @param {null | ((anchor: Node) => void)} fallback_fn
	* @returns {void}
	*/
	function each(node, flags, get_collection, get_key, render_fn, fallback_fn = null) {
		var anchor = node;
		/** @type {Map<any, EachItem>} */
		var items = /* @__PURE__ */ new Map();
		if ((flags & 4) !== 0) {
			var parent_node = node;
			anchor = hydrating ? set_hydrate_node(/* @__PURE__ */ get_first_child(parent_node)) : parent_node.appendChild(create_text());
		}
		if (hydrating) hydrate_next();
		/** @type {Effect | null} */
		var fallback = null;
		var each_array = /* @__PURE__ */ derived_safe_equal(() => {
			var collection = get_collection();
			return is_array(collection) ? collection : collection == null ? [] : array_from(collection);
		});
		/** @type {V[]} */
		var array;
		/** @type {Map<Batch, Set<any>>} */
		var pending = /* @__PURE__ */ new Map();
		var first_run = true;
		/**
		* @param {Batch} batch
		*/
		function commit(batch) {
			if ((state.effect.f & 16384) !== 0) return;
			state.pending.delete(batch);
			state.fallback = fallback;
			reconcile(state, array, anchor, flags, get_key);
			if (fallback !== null) if (array.length === 0) if ((fallback.f & 33554432) === 0) resume_effect(fallback);
			else {
				fallback.f ^= EFFECT_OFFSCREEN;
				move(fallback, null, anchor);
			}
			else pause_effect(fallback, () => {
				fallback = null;
			});
		}
		/**
		* @param {Batch} batch
		*/
		function discard(batch) {
			state.pending.delete(batch);
		}
		/** @type {EachState} */
		var state = {
			effect: block(() => {
				array = get(each_array);
				var length = array.length;
				/** `true` if there was a hydration mismatch. Needs to be a `let` or else it isn't treeshaken out */
				let mismatch = false;
				if (hydrating) {
					if (read_hydration_instruction(anchor) === "[!" !== (length === 0)) {
						anchor = skip_nodes();
						set_hydrate_node(anchor);
						set_hydrating(false);
						mismatch = true;
					}
				}
				var keys = /* @__PURE__ */ new Set();
				var batch = current_batch;
				var defer = should_defer_append();
				for (var index = 0; index < length; index += 1) {
					if (hydrating && hydrate_node.nodeType === 8 && hydrate_node.data === "]") {
						anchor = hydrate_node;
						mismatch = true;
						set_hydrating(false);
					}
					var value = array[index];
					var key = get_key(value, index);
					var item = first_run ? null : items.get(key);
					if (item) {
						if (item.v) internal_set(item.v, value);
						if (item.i) internal_set(item.i, index);
						if (defer) batch.unskip_effect(item.e);
					} else {
						item = create_item(items, first_run ? anchor : offscreen_anchor ??= create_text(), value, key, index, render_fn, flags, get_collection);
						if (!first_run) item.e.f |= EFFECT_OFFSCREEN;
						items.set(key, item);
					}
					keys.add(key);
				}
				if (length === 0 && fallback_fn && !fallback) if (first_run) fallback = branch(() => fallback_fn(anchor));
				else {
					fallback = branch(() => fallback_fn(offscreen_anchor ??= create_text()));
					fallback.f |= EFFECT_OFFSCREEN;
				}
				if (length > keys.size) each_key_duplicate("", "", "");
				if (hydrating && length > 0) set_hydrate_node(skip_nodes());
				if (!first_run) {
					pending.set(batch, keys);
					if (defer) {
						for (const [key, item] of items) if (!keys.has(key)) batch.skip_effect(item.e);
						batch.oncommit(commit);
						batch.ondiscard(discard);
					} else commit(batch);
				}
				if (mismatch) set_hydrating(true);
				get(each_array);
			}),
			flags,
			items,
			pending,
			outrogroups: null,
			fallback
		};
		first_run = false;
		if (hydrating) anchor = hydrate_node;
	}
	/**
	* Skip past any non-branch effects (which could be created with `createSubscriber`, for example) to find the next branch effect
	* @param {Effect | null} effect
	* @returns {Effect | null}
	*/
	function skip_to_branch(effect) {
		while (effect !== null && (effect.f & 32) === 0) effect = effect.next;
		return effect;
	}
	/**
	* Add, remove, or reorder items output by an each block as its input changes
	* @template V
	* @param {EachState} state
	* @param {Array<V>} array
	* @param {Element | Comment | Text} anchor
	* @param {number} flags
	* @param {(value: V, index: number) => any} get_key
	* @returns {void}
	*/
	function reconcile(state, array, anchor, flags, get_key) {
		var is_animated = (flags & 8) !== 0;
		var length = array.length;
		var items = state.items;
		var current = skip_to_branch(state.effect.first);
		/** @type {undefined | Set<Effect>} */
		var seen;
		/** @type {Effect | null} */
		var prev = null;
		/** @type {undefined | Set<Effect>} */
		var to_animate;
		/** @type {Effect[]} */
		var matched = [];
		/** @type {Effect[]} */
		var stashed = [];
		/** @type {V} */
		var value;
		/** @type {any} */
		var key;
		/** @type {Effect | undefined} */
		var effect;
		/** @type {number} */
		var i;
		if (is_animated) for (i = 0; i < length; i += 1) {
			value = array[i];
			key = get_key(value, i);
			effect = items.get(key).e;
			if ((effect.f & 33554432) === 0) {
				effect.nodes?.a?.measure();
				(to_animate ??= /* @__PURE__ */ new Set()).add(effect);
			}
		}
		for (i = 0; i < length; i += 1) {
			value = array[i];
			key = get_key(value, i);
			effect = items.get(key).e;
			if (state.outrogroups !== null) for (const group of state.outrogroups) {
				group.pending.delete(effect);
				group.done.delete(effect);
			}
			if ((effect.f & 8192) !== 0) {
				resume_effect(effect);
				if (is_animated) {
					effect.nodes?.a?.unfix();
					(to_animate ??= /* @__PURE__ */ new Set()).delete(effect);
				}
			}
			if ((effect.f & 33554432) !== 0) {
				effect.f ^= EFFECT_OFFSCREEN;
				if (effect === current) move(effect, null, anchor);
				else {
					var next = prev ? prev.next : current;
					if (effect === state.effect.last) state.effect.last = effect.prev;
					if (effect.prev) effect.prev.next = effect.next;
					if (effect.next) effect.next.prev = effect.prev;
					link(state, prev, effect);
					link(state, effect, next);
					move(effect, next, anchor);
					prev = effect;
					matched = [];
					stashed = [];
					current = skip_to_branch(prev.next);
					continue;
				}
			}
			if (effect !== current) {
				if (seen !== void 0 && seen.has(effect)) {
					if (matched.length < stashed.length) {
						var start = stashed[0];
						var j;
						prev = start.prev;
						var a = matched[0];
						var b = matched[matched.length - 1];
						for (j = 0; j < matched.length; j += 1) move(matched[j], start, anchor);
						for (j = 0; j < stashed.length; j += 1) seen.delete(stashed[j]);
						link(state, a.prev, b.next);
						link(state, prev, a);
						link(state, b, start);
						current = start;
						prev = b;
						i -= 1;
						matched = [];
						stashed = [];
					} else {
						seen.delete(effect);
						move(effect, current, anchor);
						link(state, effect.prev, effect.next);
						link(state, effect, prev === null ? state.effect.first : prev.next);
						link(state, prev, effect);
						prev = effect;
					}
					continue;
				}
				matched = [];
				stashed = [];
				while (current !== null && current !== effect) {
					(seen ??= /* @__PURE__ */ new Set()).add(current);
					stashed.push(current);
					current = skip_to_branch(current.next);
				}
				if (current === null) continue;
			}
			if ((effect.f & 33554432) === 0) matched.push(effect);
			prev = effect;
			current = skip_to_branch(effect.next);
		}
		if (state.outrogroups !== null) {
			for (const group of state.outrogroups) if (group.pending.size === 0) {
				destroy_effects(state, array_from(group.done));
				state.outrogroups?.delete(group);
			}
			if (state.outrogroups.size === 0) state.outrogroups = null;
		}
		if (current !== null || seen !== void 0) {
			/** @type {Effect[]} */
			var to_destroy = [];
			if (seen !== void 0) {
				for (effect of seen) if ((effect.f & 8192) === 0) to_destroy.push(effect);
			}
			while (current !== null) {
				if ((current.f & 8192) === 0 && current !== state.fallback) to_destroy.push(current);
				current = skip_to_branch(current.next);
			}
			var destroy_length = to_destroy.length;
			if (destroy_length > 0) {
				var controlled_anchor = (flags & 4) !== 0 && length === 0 ? anchor : null;
				if (is_animated) {
					for (i = 0; i < destroy_length; i += 1) to_destroy[i].nodes?.a?.measure();
					for (i = 0; i < destroy_length; i += 1) to_destroy[i].nodes?.a?.fix();
				}
				pause_effects(state, to_destroy, controlled_anchor);
			}
		}
		if (is_animated) queue_micro_task(() => {
			if (to_animate === void 0) return;
			for (effect of to_animate) effect.nodes?.a?.apply();
		});
	}
	/**
	* @template V
	* @param {Map<any, EachItem>} items
	* @param {Node} anchor
	* @param {V} value
	* @param {unknown} key
	* @param {number} index
	* @param {(anchor: Node, item: V | Source<V>, index: number | Value<number>, collection: () => V[]) => void} render_fn
	* @param {number} flags
	* @param {() => V[]} get_collection
	* @returns {EachItem}
	*/
	function create_item(items, anchor, value, key, index, render_fn, flags, get_collection) {
		var v = (flags & 1) !== 0 ? (flags & 16) === 0 ? /* @__PURE__ */ mutable_source(value, false, false) : source(value) : null;
		var i = (flags & 2) !== 0 ? source(index) : null;
		return {
			v,
			i,
			e: branch(() => {
				render_fn(anchor, v ?? value, i ?? index, get_collection);
				return () => {
					items.delete(key);
				};
			})
		};
	}
	/**
	* @param {Effect} effect
	* @param {Effect | null} next
	* @param {Text | Element | Comment} anchor
	*/
	function move(effect, next, anchor) {
		if (!effect.nodes) return;
		var node = effect.nodes.start;
		var end = effect.nodes.end;
		var dest = next && (next.f & 33554432) === 0 ? next.nodes.start : anchor;
		while (node !== null) {
			var next_node = /* @__PURE__ */ get_next_sibling(node);
			dest.before(node);
			if (node === end) return;
			node = next_node;
		}
	}
	/**
	* @param {EachState} state
	* @param {Effect | null} prev
	* @param {Effect | null} next
	*/
	function link(state, prev, next) {
		if (prev === null) state.effect.first = next;
		else prev.next = next;
		if (next === null) state.effect.last = prev;
		else next.prev = prev;
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/dom/blocks/slot.js
	/**
	* @param {Comment} anchor
	* @param {Record<string, any>} $$props
	* @param {string} name
	* @param {Record<string, unknown>} slot_props
	* @param {null | ((anchor: Comment) => void)} fallback_fn
	*/
	function slot(anchor, $$props, name, slot_props, fallback_fn) {
		if (hydrating) hydrate_next();
		var slot_fn = $$props.$$slots?.[name];
		var is_interop = false;
		if (slot_fn === true) {
			slot_fn = $$props[name === "default" ? "children" : name];
			is_interop = true;
		}
		if (slot_fn === void 0) {
			if (fallback_fn !== null) fallback_fn(anchor);
		} else slot_fn(anchor, is_interop ? () => slot_props : slot_props);
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/dom/blocks/svelte-component.js
	/** @import { TemplateNode, Dom } from '#client' */
	/**
	* @template P
	* @template {(props: P) => void} C
	* @param {TemplateNode} node
	* @param {() => C} get_component
	* @param {(anchor: TemplateNode, component: C) => Dom | void} render_fn
	* @returns {void}
	*/
	function component(node, get_component, render_fn) {
		/** @type {TemplateNode | undefined} */
		var hydration_start_node;
		if (hydrating) {
			hydration_start_node = hydrate_node;
			hydrate_next();
		}
		var branches = new BranchManager(node);
		block(() => {
			var component = get_component() ?? null;
			if (hydrating) {
				if (read_hydration_instruction(hydration_start_node) === "[" !== (component !== null)) {
					var anchor = skip_nodes();
					set_hydrate_node(anchor);
					branches.anchor = anchor;
					set_hydrating(false);
					branches.ensure(component, component && ((target) => render_fn(target, component)));
					set_hydrating(true);
					return;
				}
			}
			branches.ensure(component, component && ((target) => render_fn(target, component)));
		}, EFFECT_TRANSPARENT);
	}
	/** @param {Effect | null} v */
	function set_animation_effect_override(v) {}
	//#endregion
	//#region node_modules/svelte/src/internal/client/dom/blocks/svelte-element.js
	/** @import { Effect, EffectNodes, TemplateNode } from '#client' */
	/**
	* @param {Comment | Element} node
	* @param {() => string} get_tag
	* @param {boolean} is_svg
	* @param {undefined | ((element: Element, anchor: Node | null) => void)} render_fn,
	* @param {undefined | (() => string)} get_namespace
	* @param {undefined | [number, number]} location
	* @returns {void}
	*/
	function element(node, get_tag, is_svg, render_fn, get_namespace, location) {
		let was_hydrating = hydrating;
		if (hydrating) hydrate_next();
		/** @type {null | Element} */
		var element = null;
		if (hydrating && hydrate_node.nodeType === 1) {
			element = hydrate_node;
			hydrate_next();
		}
		var anchor = hydrating ? hydrate_node : node;
		/**
		* We track this so we can set it when changing the element, allowing any
		* `animate:` directive to bind itself to the correct block
		*/
		var parent_effect = active_effect;
		var branches = new BranchManager(anchor, false);
		block(() => {
			const next_tag = get_tag() || null;
			var ns = get_namespace ? get_namespace() : is_svg || next_tag === "svg" ? NAMESPACE_SVG : void 0;
			if (next_tag === null) {
				branches.ensure(null, null);
				set_should_intro(true);
				return;
			}
			branches.ensure(next_tag, (anchor) => {
				if (next_tag) {
					element = hydrating ? element : create_element(next_tag, ns);
					assign_nodes(element, element);
					if (render_fn) {
						if (hydrating && is_raw_text_element(next_tag)) element.append(document.createComment(""));
						var child_anchor = hydrating ? /* @__PURE__ */ get_first_child(element) : element.appendChild(create_text());
						if (hydrating) if (child_anchor === null) set_hydrating(false);
						else set_hydrate_node(child_anchor);
						set_animation_effect_override(parent_effect);
						render_fn(element, child_anchor);
						set_animation_effect_override(null);
					}
					/** @type {Effect & { nodes: EffectNodes }} */ active_effect.nodes.end = element;
					anchor.before(element);
				}
				if (hydrating) set_hydrate_node(anchor);
			});
			set_should_intro(true);
			return () => {
				if (next_tag) set_should_intro(false);
			};
		}, EFFECT_TRANSPARENT);
		teardown(() => {
			set_should_intro(true);
		});
		if (was_hydrating) {
			set_hydrating(true);
			set_hydrate_node(anchor);
		}
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/dom/blocks/svelte-head.js
	/** @import { TemplateNode } from '#client' */
	/**
	* @param {string} hash
	* @param {(anchor: Node) => void} render_fn
	* @returns {void}
	*/
	function head(hash, render_fn) {
		let previous_hydrate_node = null;
		let was_hydrating = hydrating;
		/** @type {Comment | Text} */
		var anchor;
		if (hydrating) {
			previous_hydrate_node = hydrate_node;
			var head_anchor = /* @__PURE__ */ get_first_child(document.head);
			while (head_anchor !== null && (head_anchor.nodeType !== 8 || head_anchor.data !== hash)) head_anchor = /* @__PURE__ */ get_next_sibling(head_anchor);
			if (head_anchor === null) set_hydrating(false);
			else {
				var start = /* @__PURE__ */ get_next_sibling(head_anchor);
				head_anchor.remove();
				set_hydrate_node(start);
			}
		}
		if (!hydrating) anchor = document.head.appendChild(create_text());
		try {
			block(() => render_fn(anchor), HEAD_EFFECT | EFFECT_PRESERVED);
		} finally {
			if (was_hydrating) {
				set_hydrating(true);
				set_hydrate_node(previous_hydrate_node);
			}
		}
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/dom/elements/attachments.js
	/** @import { Effect } from '#client' */
	/**
	* @param {Element} node
	* @param {() => (node: Element) => void} get_fn
	*/
	function attach(node, get_fn) {
		/** @type {false | undefined | ((node: Element) => void)} */
		var fn = void 0;
		/** @type {Effect | null} */
		var e;
		managed(() => {
			if (fn !== (fn = get_fn())) {
				if (e) {
					destroy_effect(e);
					e = null;
				}
				if (fn) e = branch(() => {
					effect(() => fn(node));
				});
			}
		});
	}
	//#endregion
	//#region node_modules/clsx/dist/clsx.mjs
	function r(e) {
		var t, f, n = "";
		if ("string" == typeof e || "number" == typeof e) n += e;
		else if ("object" == typeof e) if (Array.isArray(e)) {
			var o = e.length;
			for (t = 0; t < o; t++) e[t] && (f = r(e[t])) && (n && (n += " "), n += f);
		} else for (f in e) e[f] && (n && (n += " "), n += f);
		return n;
	}
	function clsx$1() {
		for (var e, t, f = 0, n = "", o = arguments.length; f < o; f++) (e = arguments[f]) && (t = r(e)) && (n && (n += " "), n += t);
		return n;
	}
	//#endregion
	//#region node_modules/svelte/src/internal/shared/attributes.js
	/**
	* Small wrapper around clsx to preserve Svelte's (weird) handling of falsy values.
	* TODO Svelte 6 revisit this, and likely turn all falsy values into the empty string (what clsx also does)
	* @param  {any} value
	*/
	function clsx(value) {
		if (typeof value === "object") return clsx$1(value);
		else return value ?? "";
	}
	var whitespace = [..." 	\n\r\f\xA0\v﻿"];
	/**
	* @param {any} value
	* @param {string | null} [hash]
	* @param {Record<string, boolean>} [directives]
	* @returns {string | null}
	*/
	function to_class(value, hash, directives) {
		var classname = value == null ? "" : "" + value;
		if (hash) classname = classname ? classname + " " + hash : hash;
		if (directives) {
			for (var key of Object.keys(directives)) if (directives[key]) classname = classname ? classname + " " + key : key;
			else if (classname.length) {
				var len = key.length;
				var a = 0;
				while ((a = classname.indexOf(key, a)) >= 0) {
					var b = a + len;
					if ((a === 0 || whitespace.includes(classname[a - 1])) && (b === classname.length || whitespace.includes(classname[b]))) classname = (a === 0 ? "" : classname.substring(0, a)) + classname.substring(b + 1);
					else a = b;
				}
			}
		}
		return classname === "" ? null : classname;
	}
	/**
	*
	* @param {Record<string,any>} styles
	* @param {boolean} important
	*/
	function append_styles(styles, important = false) {
		var separator = important ? " !important;" : ";";
		var css = "";
		for (var key of Object.keys(styles)) {
			var value = styles[key];
			if (value != null && value !== "") css += " " + key + ": " + value + separator;
		}
		return css;
	}
	/**
	* @param {string} name
	* @returns {string}
	*/
	function to_css_name(name) {
		if (name[0] !== "-" || name[1] !== "-") return name.toLowerCase();
		return name;
	}
	/**
	* @param {any} value
	* @param {Record<string, any> | [Record<string, any>, Record<string, any>]} [styles]
	* @returns {string | null}
	*/
	function to_style(value, styles) {
		if (styles) {
			var new_style = "";
			/** @type {Record<string,any> | undefined} */
			var normal_styles;
			/** @type {Record<string,any> | undefined} */
			var important_styles;
			if (Array.isArray(styles)) {
				normal_styles = styles[0];
				important_styles = styles[1];
			} else normal_styles = styles;
			if (value) {
				value = String(value).replaceAll(/\s*\/\*.*?\*\/\s*/g, "").trim();
				/** @type {boolean | '"' | "'"} */
				var in_str = false;
				var in_apo = 0;
				var in_comment = false;
				var reserved_names = [];
				if (normal_styles) reserved_names.push(...Object.keys(normal_styles).map(to_css_name));
				if (important_styles) reserved_names.push(...Object.keys(important_styles).map(to_css_name));
				var start_index = 0;
				var name_index = -1;
				const len = value.length;
				for (var i = 0; i < len; i++) {
					var c = value[i];
					if (in_comment) {
						if (c === "/" && value[i - 1] === "*") in_comment = false;
					} else if (in_str) {
						if (in_str === c) in_str = false;
					} else if (c === "/" && value[i + 1] === "*") in_comment = true;
					else if (c === "\"" || c === "'") in_str = c;
					else if (c === "(") in_apo++;
					else if (c === ")") in_apo--;
					if (!in_comment && in_str === false && in_apo === 0) {
						if (c === ":" && name_index === -1) name_index = i;
						else if (c === ";" || i === len - 1) {
							if (name_index !== -1) {
								var name = to_css_name(value.substring(start_index, name_index).trim());
								if (!reserved_names.includes(name)) {
									if (c !== ";") i++;
									var property = value.substring(start_index, i).trim();
									new_style += " " + property + ";";
								}
							}
							start_index = i + 1;
							name_index = -1;
						}
					}
				}
			}
			if (normal_styles) new_style += append_styles(normal_styles);
			if (important_styles) new_style += append_styles(important_styles, true);
			new_style = new_style.trim();
			return new_style === "" ? null : new_style;
		}
		return value == null ? null : String(value);
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/dom/elements/class.js
	/**
	* @param {Element} dom
	* @param {boolean | number} is_html
	* @param {string | null} value
	* @param {string} [hash]
	* @param {Record<string, any>} [prev_classes]
	* @param {Record<string, any>} [next_classes]
	* @returns {Record<string, boolean> | undefined}
	*/
	function set_class(dom, is_html, value, hash, prev_classes, next_classes) {
		var prev = dom.__className;
		if (hydrating || prev !== value || prev === void 0) {
			var next_class_name = to_class(value, hash, next_classes);
			if (!hydrating || next_class_name !== dom.getAttribute("class")) if (next_class_name == null) dom.removeAttribute("class");
			else if (is_html) dom.className = next_class_name;
			else dom.setAttribute("class", next_class_name);
			dom.__className = value;
		} else if (next_classes && prev_classes !== next_classes) for (var key in next_classes) {
			var is_present = !!next_classes[key];
			if (prev_classes == null || is_present !== !!prev_classes[key]) dom.classList.toggle(key, is_present);
		}
		return next_classes;
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/dom/elements/style.js
	/**
	* @param {Element & ElementCSSInlineStyle} dom
	* @param {Record<string, any>} prev
	* @param {Record<string, any>} next
	* @param {string} [priority]
	*/
	function update_styles(dom, prev = {}, next, priority) {
		for (var key in next) {
			var value = next[key];
			if (prev[key] !== value) if (next[key] == null) dom.style.removeProperty(key);
			else dom.style.setProperty(key, value, priority);
		}
	}
	/**
	* @param {Element & ElementCSSInlineStyle} dom
	* @param {string | null} value
	* @param {Record<string, any> | [Record<string, any>, Record<string, any>]} [prev_styles]
	* @param {Record<string, any> | [Record<string, any>, Record<string, any>]} [next_styles]
	*/
	function set_style(dom, value, prev_styles, next_styles) {
		var prev = dom.__style;
		if (hydrating || prev !== value) {
			var next_style_attr = to_style(value, next_styles);
			if (!hydrating || next_style_attr !== dom.getAttribute("style")) if (next_style_attr == null) dom.removeAttribute("style");
			else dom.style.cssText = next_style_attr;
			dom.__style = value;
		} else if (next_styles) if (Array.isArray(next_styles)) {
			update_styles(dom, prev_styles?.[0], next_styles[0]);
			update_styles(dom, prev_styles?.[1], next_styles[1], "important");
		} else update_styles(dom, prev_styles, next_styles);
		return next_styles;
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/dom/elements/bindings/select.js
	/**
	* Selects the correct option(s) (depending on whether this is a multiple select)
	* @template V
	* @param {HTMLSelectElement} select
	* @param {V} value
	* @param {boolean} mounting
	*/
	function select_option(select, value, mounting = false) {
		if (select.multiple) {
			if (value == void 0) return;
			if (!is_array(value)) return select_multiple_invalid_value();
			for (var option of select.options) option.selected = value.includes(get_option_value(option));
			return;
		}
		for (option of select.options) if (is(get_option_value(option), value)) {
			option.selected = true;
			return;
		}
		if (!mounting || value !== void 0) select.selectedIndex = -1;
	}
	/**
	* Selects the correct option(s) if `value` is given,
	* and then sets up a mutation observer to sync the
	* current selection to the dom when it changes. Such
	* changes could for example occur when options are
	* inside an `#each` block.
	* @param {HTMLSelectElement} select
	*/
	function init_select(select) {
		var observer = new MutationObserver(() => {
			select_option(select, select.__value);
		});
		observer.observe(select, {
			childList: true,
			subtree: true,
			attributes: true,
			attributeFilter: ["value"]
		});
		teardown(() => {
			observer.disconnect();
		});
	}
	/** @param {HTMLOptionElement} option */
	function get_option_value(option) {
		if ("__value" in option) return option.__value;
		else return option.value;
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/dom/elements/attributes.js
	/** @import { Blocker, Effect } from '#client' */
	var CLASS = Symbol("class");
	var STYLE = Symbol("style");
	var IS_CUSTOM_ELEMENT = Symbol("is custom element");
	var IS_HTML = Symbol("is html");
	var LINK_TAG = IS_XHTML ? "link" : "LINK";
	var INPUT_TAG = IS_XHTML ? "input" : "INPUT";
	var OPTION_TAG = IS_XHTML ? "option" : "OPTION";
	var SELECT_TAG = IS_XHTML ? "select" : "SELECT";
	/**
	* The value/checked attribute in the template actually corresponds to the defaultValue property, so we need
	* to remove it upon hydration to avoid a bug when someone resets the form value.
	* @param {HTMLInputElement} input
	* @returns {void}
	*/
	function remove_input_defaults(input) {
		if (!hydrating) return;
		var already_removed = false;
		var remove_defaults = () => {
			if (already_removed) return;
			already_removed = true;
			if (input.hasAttribute("value")) {
				var value = input.value;
				set_attribute(input, "value", null);
				input.value = value;
			}
			if (input.hasAttribute("checked")) {
				var checked = input.checked;
				set_attribute(input, "checked", null);
				input.checked = checked;
			}
		};
		input.__on_r = remove_defaults;
		queue_micro_task(remove_defaults);
		add_form_reset_listener();
	}
	/**
	* Sets the `selected` attribute on an `option` element.
	* Not set through the property because that doesn't reflect to the DOM,
	* which means it wouldn't be taken into account when a form is reset.
	* @param {HTMLOptionElement} element
	* @param {boolean} selected
	*/
	function set_selected(element, selected) {
		if (selected) {
			if (!element.hasAttribute("selected")) element.setAttribute("selected", "");
		} else element.removeAttribute("selected");
	}
	/**
	* @param {Element} element
	* @param {string} attribute
	* @param {string | null} value
	* @param {boolean} [skip_warning]
	*/
	function set_attribute(element, attribute, value, skip_warning) {
		var attributes = get_attributes(element);
		if (hydrating) {
			attributes[attribute] = element.getAttribute(attribute);
			if (attribute === "src" || attribute === "srcset" || attribute === "href" && element.nodeName === LINK_TAG) {
				if (!skip_warning) check_src_in_dev_hydration(element, attribute, value ?? "");
				return;
			}
		}
		if (attributes[attribute] === (attributes[attribute] = value)) return;
		if (attribute === "loading") element[LOADING_ATTR_SYMBOL] = value;
		if (value == null) element.removeAttribute(attribute);
		else if (typeof value !== "string" && get_setters(element).includes(attribute)) element[attribute] = value;
		else element.setAttribute(attribute, value);
	}
	/**
	* Spreads attributes onto a DOM element, taking into account the currently set attributes
	* @param {Element & ElementCSSInlineStyle} element
	* @param {Record<string | symbol, any> | undefined} prev
	* @param {Record<string | symbol, any>} next New attributes - this function mutates this object
	* @param {string} [css_hash]
	* @param {boolean} [should_remove_defaults]
	* @param {boolean} [skip_warning]
	* @returns {Record<string, any>}
	*/
	function set_attributes(element, prev, next, css_hash, should_remove_defaults = false, skip_warning = false) {
		if (hydrating && should_remove_defaults && element.nodeName === INPUT_TAG) {
			var input = element;
			if (!((input.type === "checkbox" ? "defaultChecked" : "defaultValue") in next)) remove_input_defaults(input);
		}
		var attributes = get_attributes(element);
		var is_custom_element = attributes[IS_CUSTOM_ELEMENT];
		var preserve_attribute_case = !attributes[IS_HTML];
		let is_hydrating_custom_element = hydrating && is_custom_element;
		if (is_hydrating_custom_element) set_hydrating(false);
		var current = prev || {};
		var is_option_element = element.nodeName === OPTION_TAG;
		for (var key in prev) if (!(key in next)) next[key] = null;
		if (next.class) next.class = clsx(next.class);
		else if (css_hash || next[CLASS]) next.class = null;
		if (next[STYLE]) next.style ??= null;
		var setters = get_setters(element);
		for (const key in next) {
			let value = next[key];
			if (is_option_element && key === "value" && value == null) {
				element.value = element.__value = "";
				current[key] = value;
				continue;
			}
			if (key === "class") {
				set_class(element, element.namespaceURI === "http://www.w3.org/1999/xhtml", value, css_hash, prev?.[CLASS], next[CLASS]);
				current[key] = value;
				current[CLASS] = next[CLASS];
				continue;
			}
			if (key === "style") {
				set_style(element, value, prev?.[STYLE], next[STYLE]);
				current[key] = value;
				current[STYLE] = next[STYLE];
				continue;
			}
			var prev_value = current[key];
			if (value === prev_value && !(value === void 0 && element.hasAttribute(key))) continue;
			current[key] = value;
			var prefix = key[0] + key[1];
			if (prefix === "$$") continue;
			if (prefix === "on") {
				/** @type {{ capture?: true }} */
				const opts = {};
				const event_handle_key = "$$" + key;
				let event_name = key.slice(2);
				var is_delegated = can_delegate_event(event_name);
				if (is_capture_event(event_name)) {
					event_name = event_name.slice(0, -7);
					opts.capture = true;
				}
				if (!is_delegated && prev_value) {
					if (value != null) continue;
					element.removeEventListener(event_name, current[event_handle_key], opts);
					current[event_handle_key] = null;
				}
				if (is_delegated) {
					delegated(event_name, element, value);
					delegate([event_name]);
				} else if (value != null) {
					/**
					* @this {any}
					* @param {Event} evt
					*/
					function handle(evt) {
						current[key].call(this, evt);
					}
					current[event_handle_key] = create_event(event_name, element, handle, opts);
				}
			} else if (key === "style") set_attribute(element, key, value);
			else if (key === "autofocus") autofocus(element, Boolean(value));
			else if (!is_custom_element && (key === "__value" || key === "value" && value != null)) element.value = element.__value = value;
			else if (key === "selected" && is_option_element) set_selected(element, value);
			else {
				var name = key;
				if (!preserve_attribute_case) name = normalize_attribute(name);
				var is_default = name === "defaultValue" || name === "defaultChecked";
				if (value == null && !is_custom_element && !is_default) {
					attributes[key] = null;
					if (name === "value" || name === "checked") {
						let input = element;
						const use_default = prev === void 0;
						if (name === "value") {
							let previous = input.defaultValue;
							input.removeAttribute(name);
							input.defaultValue = previous;
							input.value = input.__value = use_default ? previous : null;
						} else {
							let previous = input.defaultChecked;
							input.removeAttribute(name);
							input.defaultChecked = previous;
							input.checked = use_default ? previous : false;
						}
					} else element.removeAttribute(key);
				} else if (is_default || setters.includes(name) && (is_custom_element || typeof value !== "string")) {
					element[name] = value;
					if (name in attributes) attributes[name] = UNINITIALIZED;
				} else if (typeof value !== "function") set_attribute(element, name, value, skip_warning);
			}
		}
		if (is_hydrating_custom_element) set_hydrating(true);
		return current;
	}
	/**
	* @param {Element & ElementCSSInlineStyle} element
	* @param {(...expressions: any) => Record<string | symbol, any>} fn
	* @param {Array<() => any>} sync
	* @param {Array<() => Promise<any>>} async
	* @param {Blocker[]} blockers
	* @param {string} [css_hash]
	* @param {boolean} [should_remove_defaults]
	* @param {boolean} [skip_warning]
	*/
	function attribute_effect(element, fn, sync = [], async = [], blockers = [], css_hash, should_remove_defaults = false, skip_warning = false) {
		flatten(blockers, sync, async, (values) => {
			/** @type {Record<string | symbol, any> | undefined} */
			var prev = void 0;
			/** @type {Record<symbol, Effect>} */
			var effects = {};
			var is_select = element.nodeName === SELECT_TAG;
			var inited = false;
			managed(() => {
				var next = fn(...values.map(get));
				/** @type {Record<string | symbol, any>} */
				var current = set_attributes(element, prev, next, css_hash, should_remove_defaults, skip_warning);
				if (inited && is_select && "value" in next) select_option(element, next.value);
				for (let symbol of Object.getOwnPropertySymbols(effects)) if (!next[symbol]) destroy_effect(effects[symbol]);
				for (let symbol of Object.getOwnPropertySymbols(next)) {
					var n = next[symbol];
					if (symbol.description === "@attach" && (!prev || n !== prev[symbol])) {
						if (effects[symbol]) destroy_effect(effects[symbol]);
						effects[symbol] = branch(() => attach(element, () => n));
					}
					current[symbol] = n;
				}
				prev = current;
			});
			if (is_select) {
				var select = element;
				effect(() => {
					select_option(
						select,
						/** @type {Record<string | symbol, any>} */
						prev.value,
						true
					);
					init_select(select);
				});
			}
			inited = true;
		});
	}
	/**
	*
	* @param {Element} element
	*/
	function get_attributes(element) {
		return element.__attributes ??= {
			[IS_CUSTOM_ELEMENT]: element.nodeName.includes("-"),
			[IS_HTML]: element.namespaceURI === NAMESPACE_HTML
		};
	}
	/** @type {Map<string, string[]>} */
	var setters_cache = /* @__PURE__ */ new Map();
	/** @param {Element} element */
	function get_setters(element) {
		var cache_key = element.getAttribute("is") || element.nodeName;
		var setters = setters_cache.get(cache_key);
		if (setters) return setters;
		setters_cache.set(cache_key, setters = []);
		var descriptors;
		var proto = element;
		var element_proto = Element.prototype;
		while (element_proto !== proto) {
			descriptors = get_descriptors(proto);
			for (var key in descriptors) if (descriptors[key].set) setters.push(key);
			proto = get_prototype_of(proto);
		}
		return setters;
	}
	/**
	* @param {any} element
	* @param {string} attribute
	* @param {string} value
	*/
	function check_src_in_dev_hydration(element, attribute, value) {}
	//#endregion
	//#region node_modules/svelte/src/internal/client/dom/elements/bindings/input.js
	/** @import { Batch } from '../../../reactivity/batch.js' */
	/**
	* @param {HTMLInputElement} input
	* @param {() => unknown} get
	* @param {(value: unknown) => void} set
	* @returns {void}
	*/
	function bind_value(input, get, set = get) {
		var batches = /* @__PURE__ */ new WeakSet();
		listen_to_event_and_reset_event(input, "input", async (is_reset) => {
			/** @type {any} */
			var value = is_reset ? input.defaultValue : input.value;
			value = is_numberlike_input(input) ? to_number(value) : value;
			set(value);
			if (current_batch !== null) batches.add(current_batch);
			await tick();
			if (value !== (value = get())) {
				var start = input.selectionStart;
				var end = input.selectionEnd;
				var length = input.value.length;
				input.value = value ?? "";
				if (end !== null) {
					var new_length = input.value.length;
					if (start === end && end === length && new_length > length) {
						input.selectionStart = new_length;
						input.selectionEnd = new_length;
					} else {
						input.selectionStart = start;
						input.selectionEnd = Math.min(end, new_length);
					}
				}
			}
		});
		if (hydrating && input.defaultValue !== input.value || untrack(get) == null && input.value) {
			set(is_numberlike_input(input) ? to_number(input.value) : input.value);
			if (current_batch !== null) batches.add(current_batch);
		}
		render_effect(() => {
			var value = get();
			if (input === document.activeElement) {
				var batch = async_mode_flag ? previous_batch : current_batch;
				if (batches.has(batch)) return;
			}
			if (is_numberlike_input(input) && value === to_number(input.value)) return;
			if (input.type === "date" && !value && !input.value) return;
			if (value !== input.value) input.value = value ?? "";
		});
	}
	/**
	* @param {HTMLInputElement} input
	*/
	function is_numberlike_input(input) {
		var type = input.type;
		return type === "number" || type === "range";
	}
	/**
	* @param {string} value
	*/
	function to_number(value) {
		return value === "" ? null : +value;
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/dom/elements/bindings/this.js
	/** @import { ComponentContext, Effect } from '#client' */
	/**
	* @param {any} bound_value
	* @param {Element} element_or_component
	* @returns {boolean}
	*/
	function is_bound_this(bound_value, element_or_component) {
		return bound_value === element_or_component || bound_value?.[STATE_SYMBOL] === element_or_component;
	}
	/**
	* @param {any} element_or_component
	* @param {(value: unknown, ...parts: unknown[]) => void} update
	* @param {(...parts: unknown[]) => unknown} get_value
	* @param {() => unknown[]} [get_parts] Set if the this binding is used inside an each block,
	* 										returns all the parts of the each block context that are used in the expression
	* @returns {void}
	*/
	function bind_this(element_or_component = {}, update, get_value, get_parts) {
		var component_effect = component_context.r;
		var parent = active_effect;
		effect(() => {
			/** @type {unknown[]} */
			var old_parts;
			/** @type {unknown[]} */
			var parts;
			render_effect(() => {
				old_parts = parts;
				parts = get_parts?.() || [];
				untrack(() => {
					if (element_or_component !== get_value(...parts)) {
						update(element_or_component, ...parts);
						if (old_parts && is_bound_this(get_value(...old_parts), element_or_component)) update(null, ...old_parts);
					}
				});
			});
			return () => {
				let p = parent;
				while (p !== component_effect && p.parent !== null && p.parent.f & 33554432) p = p.parent;
				const teardown = () => {
					if (parts && is_bound_this(get_value(...parts), element_or_component)) update(null, ...parts);
				};
				const original_teardown = p.teardown;
				p.teardown = () => {
					teardown();
					original_teardown?.();
				};
			};
		});
		return element_or_component;
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/dom/legacy/lifecycle.js
	/** @import { ComponentContextLegacy } from '#client' */
	/**
	* Legacy-mode only: Call `onMount` callbacks and set up `beforeUpdate`/`afterUpdate` effects
	* @param {boolean} [immutable]
	*/
	function init(immutable = false) {
		const context = component_context;
		const callbacks = context.l.u;
		if (!callbacks) return;
		let props = () => deep_read_state(context.s);
		if (immutable) {
			let version = 0;
			let prev = {};
			const d = /* @__PURE__ */ derived(() => {
				let changed = false;
				const props = context.s;
				for (const key in props) if (props[key] !== prev[key]) {
					prev[key] = props[key];
					changed = true;
				}
				if (changed) version++;
				return version;
			});
			props = () => get(d);
		}
		if (callbacks.b.length) user_pre_effect(() => {
			observe_all(context, props);
			run_all(callbacks.b);
		});
		user_effect(() => {
			const fns = untrack(() => callbacks.m.map(run));
			return () => {
				for (const fn of fns) if (typeof fn === "function") fn();
			};
		});
		if (callbacks.a.length) user_effect(() => {
			observe_all(context, props);
			run_all(callbacks.a);
		});
	}
	/**
	* Invoke the getter of all signals associated with a component
	* so they can be registered to the effect this function is called in.
	* @param {ComponentContextLegacy} context
	* @param {(() => void)} props
	*/
	function observe_all(context, props) {
		if (context.l.s) for (const signal of context.l.s) get(signal);
		props();
	}
	//#endregion
	//#region node_modules/svelte/src/internal/client/reactivity/props.js
	/** @import { Effect, Source } from './types.js' */
	/**
	* The proxy handler for legacy $$restProps and $$props
	* @type {ProxyHandler<{ props: Record<string | symbol, unknown>, exclude: Array<string | symbol>, special: Record<string | symbol, (v?: unknown) => unknown>, version: Source<number>, parent_effect: Effect }>}}
	*/
	var legacy_rest_props_handler = {
		get(target, key) {
			if (target.exclude.includes(key)) return;
			get(target.version);
			return key in target.special ? target.special[key]() : target.props[key];
		},
		set(target, key, value) {
			if (!(key in target.special)) {
				var previous_effect = active_effect;
				try {
					set_active_effect(target.parent_effect);
					/** @type {Record<string, (v?: unknown) => unknown>} */
					target.special[key] = prop({ get [key]() {
						return target.props[key];
					} }, key, 4);
				} finally {
					set_active_effect(previous_effect);
				}
			}
			target.special[key](value);
			update(target.version);
			return true;
		},
		getOwnPropertyDescriptor(target, key) {
			if (target.exclude.includes(key)) return;
			if (key in target.props) return {
				enumerable: true,
				configurable: true,
				value: target.props[key]
			};
		},
		deleteProperty(target, key) {
			if (target.exclude.includes(key)) return true;
			target.exclude.push(key);
			update(target.version);
			return true;
		},
		has(target, key) {
			if (target.exclude.includes(key)) return false;
			return key in target.props;
		},
		ownKeys(target) {
			return Reflect.ownKeys(target.props).filter((key) => !target.exclude.includes(key));
		}
	};
	/**
	* @param {Record<string, unknown>} props
	* @param {string[]} exclude
	* @returns {Record<string, unknown>}
	*/
	function legacy_rest_props(props, exclude) {
		return new Proxy({
			props,
			exclude,
			special: {},
			version: source(0),
			parent_effect: active_effect
		}, legacy_rest_props_handler);
	}
	/**
	* The proxy handler for spread props. Handles the incoming array of props
	* that looks like `() => { dynamic: props }, { static: prop }, ..` and wraps
	* them so that the whole thing is passed to the component as the `$$props` argument.
	* @type {ProxyHandler<{ props: Array<Record<string | symbol, unknown> | (() => Record<string | symbol, unknown>)> }>}}
	*/
	var spread_props_handler = {
		get(target, key) {
			let i = target.props.length;
			while (i--) {
				let p = target.props[i];
				if (is_function(p)) p = p();
				if (typeof p === "object" && p !== null && key in p) return p[key];
			}
		},
		set(target, key, value) {
			let i = target.props.length;
			while (i--) {
				let p = target.props[i];
				if (is_function(p)) p = p();
				const desc = get_descriptor(p, key);
				if (desc && desc.set) {
					desc.set(value);
					return true;
				}
			}
			return false;
		},
		getOwnPropertyDescriptor(target, key) {
			let i = target.props.length;
			while (i--) {
				let p = target.props[i];
				if (is_function(p)) p = p();
				if (typeof p === "object" && p !== null && key in p) {
					const descriptor = get_descriptor(p, key);
					if (descriptor && !descriptor.configurable) descriptor.configurable = true;
					return descriptor;
				}
			}
		},
		has(target, key) {
			if (key === STATE_SYMBOL || key === LEGACY_PROPS) return false;
			for (let p of target.props) {
				if (is_function(p)) p = p();
				if (p != null && key in p) return true;
			}
			return false;
		},
		ownKeys(target) {
			/** @type {Array<string | symbol>} */
			const keys = [];
			for (let p of target.props) {
				if (is_function(p)) p = p();
				if (!p) continue;
				for (const key in p) if (!keys.includes(key)) keys.push(key);
				for (const key of Object.getOwnPropertySymbols(p)) if (!keys.includes(key)) keys.push(key);
			}
			return keys;
		}
	};
	/**
	* @param {Array<Record<string, unknown> | (() => Record<string, unknown>)>} props
	* @returns {any}
	*/
	function spread_props(...props) {
		return new Proxy({ props }, spread_props_handler);
	}
	/**
	* This function is responsible for synchronizing a possibly bound prop with the inner component state.
	* It is used whenever the compiler sees that the component writes to the prop, or when it has a default prop_value.
	* @template V
	* @param {Record<string, unknown>} props
	* @param {string} key
	* @param {number} flags
	* @param {V | (() => V)} [fallback]
	* @returns {(() => V | ((arg: V) => V) | ((arg: V, mutation: boolean) => V))}
	*/
	function prop(props, key, flags, fallback) {
		var runes = !legacy_mode_flag || (flags & 2) !== 0;
		var bindable = (flags & 8) !== 0;
		var lazy = (flags & 16) !== 0;
		var fallback_value = fallback;
		var fallback_dirty = true;
		var get_fallback = () => {
			if (fallback_dirty) {
				fallback_dirty = false;
				fallback_value = lazy ? untrack(fallback) : fallback;
			}
			return fallback_value;
		};
		/** @type {((v: V) => void) | undefined} */
		let setter;
		if (bindable) {
			var is_entry_props = STATE_SYMBOL in props || LEGACY_PROPS in props;
			setter = get_descriptor(props, key)?.set ?? (is_entry_props && key in props ? (v) => props[key] = v : void 0);
		}
		/** @type {V} */
		var initial_value;
		var is_store_sub = false;
		if (bindable) [initial_value, is_store_sub] = capture_store_binding(() => props[key]);
		else initial_value = props[key];
		if (initial_value === void 0 && fallback !== void 0) {
			initial_value = get_fallback();
			if (setter) {
				if (runes) props_invalid_value(key);
				setter(initial_value);
			}
		}
		/** @type {() => V} */
		var getter;
		if (runes) getter = () => {
			var value = props[key];
			if (value === void 0) return get_fallback();
			fallback_dirty = true;
			return value;
		};
		else getter = () => {
			var value = props[key];
			if (value !== void 0) fallback_value = void 0;
			return value === void 0 ? fallback_value : value;
		};
		if (runes && (flags & 4) === 0) return getter;
		if (setter) {
			var legacy_parent = props.$$legacy;
			return (function(value, mutation) {
				if (arguments.length > 0) {
					if (!runes || !mutation || legacy_parent || is_store_sub)
 /** @type {Function} */ setter(mutation ? getter() : value);
					return value;
				}
				return getter();
			});
		}
		var overridden = false;
		var d = ((flags & 1) !== 0 ? derived : derived_safe_equal)(() => {
			overridden = false;
			return getter();
		});
		if (bindable) get(d);
		var parent_effect = active_effect;
		return (function(value, mutation) {
			if (arguments.length > 0) {
				const new_value = mutation ? get(d) : runes && bindable ? proxy(value) : value;
				set(d, new_value);
				overridden = true;
				if (fallback_value !== void 0) fallback_value = new_value;
				return value;
			}
			if (is_destroying_effect && overridden || (parent_effect.f & 16384) !== 0) return d.v;
			return get(d);
		});
	}
	if (typeof HTMLElement === "function");
	/**
	* `onMount`, like [`$effect`](https://svelte.dev/docs/svelte/$effect), schedules a function to run as soon as the component has been mounted to the DOM.
	* Unlike `$effect`, the provided function only runs once.
	*
	* It must be called during the component's initialisation (but doesn't need to live _inside_ the component;
	* it can be called from an external module). If a function is returned _synchronously_ from `onMount`,
	* it will be called when the component is unmounted.
	*
	* `onMount` functions do not run during [server-side rendering](https://svelte.dev/docs/svelte/svelte-server#render).
	*
	* @template T
	* @param {() => NotFunction<T> | Promise<NotFunction<T>> | (() => any)} fn
	* @returns {void}
	*/
	function onMount(fn) {
		if (component_context === null) lifecycle_outside_component("onMount");
		if (legacy_mode_flag && component_context.l !== null) init_update_callbacks(component_context).m.push(fn);
		else user_effect(() => {
			const cleanup = untrack(fn);
			if (typeof cleanup === "function") return cleanup;
		});
	}
	/**
	* Legacy-mode: Init callbacks object for onMount/beforeUpdate/afterUpdate
	* @param {ComponentContext} context
	*/
	function init_update_callbacks(context) {
		var l = context.l;
		return l.u ??= {
			a: [],
			b: [],
			m: []
		};
	}
	//#endregion
	//#region node_modules/svelte/src/internal/disclose-version.js
	if (typeof window !== "undefined") ((window.__svelte ??= {}).v ??= /* @__PURE__ */ new Set()).add("5");
	//#endregion
	//#region node_modules/svelte/src/internal/flags/legacy.js
	enable_legacy_mode_flag();
	//#endregion
	//#region node_modules/lucide-svelte/dist/defaultAttributes.js
	/**
	* @license lucide-svelte v1.0.1 - ISC
	*
	* ISC License
	* 
	* Copyright (c) 2026 Lucide Icons and Contributors
	* 
	* Permission to use, copy, modify, and/or distribute this software for any
	* purpose with or without fee is hereby granted, provided that the above
	* copyright notice and this permission notice appear in all copies.
	* 
	* THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
	* WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
	* MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
	* ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
	* WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
	* ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
	* OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
	* 
	* ---
	* 
	* The following Lucide icons are derived from the Feather project:
	* 
	* airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
	* 
	* The MIT License (MIT) (for the icons listed above)
	* 
	* Copyright (c) 2013-present Cole Bemis
	* 
	* Permission is hereby granted, free of charge, to any person obtaining a copy
	* of this software and associated documentation files (the "Software"), to deal
	* in the Software without restriction, including without limitation the rights
	* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
	* copies of the Software, and to permit persons to whom the Software is
	* furnished to do so, subject to the following conditions:
	* 
	* The above copyright notice and this permission notice shall be included in all
	* copies or substantial portions of the Software.
	* 
	* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
	* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
	* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
	* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
	* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
	* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
	* SOFTWARE.
	* 
	*/
	var defaultAttributes = {
		xmlns: "http://www.w3.org/2000/svg",
		width: 24,
		height: 24,
		viewBox: "0 0 24 24",
		fill: "none",
		stroke: "currentColor",
		"stroke-width": 2,
		"stroke-linecap": "round",
		"stroke-linejoin": "round"
	};
	//#endregion
	//#region node_modules/lucide-svelte/dist/utils/hasA11yProp.js
	/**
	* @license lucide-svelte v1.0.1 - ISC
	*
	* ISC License
	* 
	* Copyright (c) 2026 Lucide Icons and Contributors
	* 
	* Permission to use, copy, modify, and/or distribute this software for any
	* purpose with or without fee is hereby granted, provided that the above
	* copyright notice and this permission notice appear in all copies.
	* 
	* THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
	* WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
	* MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
	* ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
	* WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
	* ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
	* OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
	* 
	* ---
	* 
	* The following Lucide icons are derived from the Feather project:
	* 
	* airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
	* 
	* The MIT License (MIT) (for the icons listed above)
	* 
	* Copyright (c) 2013-present Cole Bemis
	* 
	* Permission is hereby granted, free of charge, to any person obtaining a copy
	* of this software and associated documentation files (the "Software"), to deal
	* in the Software without restriction, including without limitation the rights
	* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
	* copies of the Software, and to permit persons to whom the Software is
	* furnished to do so, subject to the following conditions:
	* 
	* The above copyright notice and this permission notice shall be included in all
	* copies or substantial portions of the Software.
	* 
	* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
	* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
	* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
	* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
	* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
	* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
	* SOFTWARE.
	* 
	*/
	/**
	* Check if a component has an accessibility prop
	*
	* @param {object} props
	* @returns {boolean} Whether the component has an accessibility prop
	*/
	var hasA11yProp = (props) => {
		for (const prop in props) if (prop.startsWith("aria-") || prop === "role" || prop === "title") return true;
		return false;
	};
	//#endregion
	//#region node_modules/lucide-svelte/dist/utils/mergeClasses.js
	/**
	* @license lucide-svelte v1.0.1 - ISC
	*
	* ISC License
	* 
	* Copyright (c) 2026 Lucide Icons and Contributors
	* 
	* Permission to use, copy, modify, and/or distribute this software for any
	* purpose with or without fee is hereby granted, provided that the above
	* copyright notice and this permission notice appear in all copies.
	* 
	* THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
	* WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
	* MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
	* ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
	* WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
	* ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
	* OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
	* 
	* ---
	* 
	* The following Lucide icons are derived from the Feather project:
	* 
	* airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
	* 
	* The MIT License (MIT) (for the icons listed above)
	* 
	* Copyright (c) 2013-present Cole Bemis
	* 
	* Permission is hereby granted, free of charge, to any person obtaining a copy
	* of this software and associated documentation files (the "Software"), to deal
	* in the Software without restriction, including without limitation the rights
	* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
	* copies of the Software, and to permit persons to whom the Software is
	* furnished to do so, subject to the following conditions:
	* 
	* The above copyright notice and this permission notice shall be included in all
	* copies or substantial portions of the Software.
	* 
	* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
	* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
	* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
	* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
	* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
	* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
	* SOFTWARE.
	* 
	*/
	/**
	* Merges classes into a single string
	*
	* @param {array} classes
	* @returns {string} A string of classes
	*/
	var mergeClasses = (...classes) => classes.filter((className, index, array) => {
		return Boolean(className) && className.trim() !== "" && array.indexOf(className) === index;
	}).join(" ").trim();
	//#endregion
	//#region node_modules/lucide-svelte/dist/Icon.svelte
	var root$7 = /* @__PURE__ */ from_svg(`<svg><!><!></svg>`);
	function Icon($$anchor, $$props) {
		const $$sanitized_props = legacy_rest_props($$props, [
			"children",
			"$$slots",
			"$$events",
			"$$legacy"
		]);
		const $$restProps = legacy_rest_props($$sanitized_props, [
			"name",
			"color",
			"size",
			"strokeWidth",
			"absoluteStrokeWidth",
			"iconNode"
		]);
		push($$props, false);
		let name = prop($$props, "name", 8, void 0);
		let color = prop($$props, "color", 8, "currentColor");
		let size = prop($$props, "size", 8, 24);
		let strokeWidth = prop($$props, "strokeWidth", 8, 2);
		let absoluteStrokeWidth = prop($$props, "absoluteStrokeWidth", 8, false);
		let iconNode = prop($$props, "iconNode", 24, () => []);
		init();
		var svg = root$7();
		attribute_effect(svg, ($0, $1, $2) => ({
			...defaultAttributes,
			...$0,
			...$$restProps,
			width: size(),
			height: size(),
			stroke: color(),
			"stroke-width": $1,
			class: $2
		}), [
			() => !hasA11yProp($$restProps) ? { "aria-hidden": "true" } : void 0,
			() => (deep_read_state(absoluteStrokeWidth()), deep_read_state(strokeWidth()), deep_read_state(size()), untrack(() => absoluteStrokeWidth() ? Number(strokeWidth()) * 24 / Number(size()) : strokeWidth())),
			() => (deep_read_state(mergeClasses), deep_read_state(name()), deep_read_state($$sanitized_props), untrack(() => mergeClasses("lucide-icon", "lucide", name() ? `lucide-${name()}` : "", $$sanitized_props.class)))
		]);
		var node = child(svg);
		each(node, 1, iconNode, index, ($$anchor, $$item) => {
			var $$array = /* @__PURE__ */ user_derived(() => to_array(get($$item), 2));
			let tag = () => get($$array)[0];
			let attrs = () => get($$array)[1];
			var fragment = comment();
			element(first_child(fragment), tag, true, ($$element, $$anchor) => {
				attribute_effect($$element, () => ({ ...attrs() }));
			});
			append($$anchor, fragment);
		});
		slot(sibling(node), $$props, "default", {}, null);
		reset(svg);
		append($$anchor, svg);
		pop();
	}
	//#endregion
	//#region node_modules/lucide-svelte/dist/icons/arrow-left.svelte
	function Arrow_left($$anchor, $$props) {
		const $$sanitized_props = legacy_rest_props($$props, [
			"children",
			"$$slots",
			"$$events",
			"$$legacy"
		]);
		/**
		* @license lucide-svelte v1.0.1 - ISC
		*
		* ISC License
		*
		* Copyright (c) 2026 Lucide Icons and Contributors
		*
		* Permission to use, copy, modify, and/or distribute this software for any
		* purpose with or without fee is hereby granted, provided that the above
		* copyright notice and this permission notice appear in all copies.
		*
		* THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
		* WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
		* MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
		* ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
		* WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
		* ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
		* OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
		*
		* ---
		*
		* The following Lucide icons are derived from the Feather project:
		*
		* airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
		*
		* The MIT License (MIT) (for the icons listed above)
		*
		* Copyright (c) 2013-present Cole Bemis
		*
		* Permission is hereby granted, free of charge, to any person obtaining a copy
		* of this software and associated documentation files (the "Software"), to deal
		* in the Software without restriction, including without limitation the rights
		* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
		* copies of the Software, and to permit persons to whom the Software is
		* furnished to do so, subject to the following conditions:
		*
		* The above copyright notice and this permission notice shall be included in all
		* copies or substantial portions of the Software.
		*
		* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
		* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
		* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
		* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
		* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
		* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
		* SOFTWARE.
		*
		*/
		const iconNode = [["path", { "d": "m12 19-7-7 7-7" }], ["path", { "d": "M19 12H5" }]];
		/**
		* @component @name ArrowLeft
		* @description Lucide SVG icon component, renders SVG Element with children.
		*
		* @preview ![img](data:image/svg+xml;base64,PHN2ZyAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogIHdpZHRoPSIyNCIKICBoZWlnaHQ9IjI0IgogIHZpZXdCb3g9IjAgMCAyNCAyNCIKICBmaWxsPSJub25lIgogIHN0cm9rZT0iIzAwMCIgc3R5bGU9ImJhY2tncm91bmQtY29sb3I6ICNmZmY7IGJvcmRlci1yYWRpdXM6IDJweCIKICBzdHJva2Utd2lkdGg9IjIiCiAgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIgogIHN0cm9rZS1saW5lam9pbj0icm91bmQiCj4KICA8cGF0aCBkPSJtMTIgMTktNy03IDctNyIgLz4KICA8cGF0aCBkPSJNMTkgMTJINSIgLz4KPC9zdmc+Cg==) - https://lucide.dev/icons/arrow-left
		* @see https://lucide.dev/guide/packages/lucide-svelte - Documentation
		*
		* @param {Object} props - Lucide icons props and any valid SVG attribute
		* @returns {FunctionalComponent} Svelte component
		*
		*/
		Icon($$anchor, spread_props({ name: "arrow-left" }, () => $$sanitized_props, {
			get iconNode() {
				return iconNode;
			},
			children: ($$anchor, $$slotProps) => {
				var fragment_1 = comment();
				slot(first_child(fragment_1), $$props, "default", {}, null);
				append($$anchor, fragment_1);
			},
			$$slots: { default: true }
		}));
	}
	//#endregion
	//#region node_modules/lucide-svelte/dist/icons/arrow-right.svelte
	function Arrow_right($$anchor, $$props) {
		const $$sanitized_props = legacy_rest_props($$props, [
			"children",
			"$$slots",
			"$$events",
			"$$legacy"
		]);
		/**
		* @license lucide-svelte v1.0.1 - ISC
		*
		* ISC License
		*
		* Copyright (c) 2026 Lucide Icons and Contributors
		*
		* Permission to use, copy, modify, and/or distribute this software for any
		* purpose with or without fee is hereby granted, provided that the above
		* copyright notice and this permission notice appear in all copies.
		*
		* THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
		* WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
		* MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
		* ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
		* WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
		* ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
		* OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
		*
		* ---
		*
		* The following Lucide icons are derived from the Feather project:
		*
		* airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
		*
		* The MIT License (MIT) (for the icons listed above)
		*
		* Copyright (c) 2013-present Cole Bemis
		*
		* Permission is hereby granted, free of charge, to any person obtaining a copy
		* of this software and associated documentation files (the "Software"), to deal
		* in the Software without restriction, including without limitation the rights
		* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
		* copies of the Software, and to permit persons to whom the Software is
		* furnished to do so, subject to the following conditions:
		*
		* The above copyright notice and this permission notice shall be included in all
		* copies or substantial portions of the Software.
		*
		* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
		* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
		* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
		* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
		* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
		* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
		* SOFTWARE.
		*
		*/
		const iconNode = [["path", { "d": "M5 12h14" }], ["path", { "d": "m12 5 7 7-7 7" }]];
		/**
		* @component @name ArrowRight
		* @description Lucide SVG icon component, renders SVG Element with children.
		*
		* @preview ![img](data:image/svg+xml;base64,PHN2ZyAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogIHdpZHRoPSIyNCIKICBoZWlnaHQ9IjI0IgogIHZpZXdCb3g9IjAgMCAyNCAyNCIKICBmaWxsPSJub25lIgogIHN0cm9rZT0iIzAwMCIgc3R5bGU9ImJhY2tncm91bmQtY29sb3I6ICNmZmY7IGJvcmRlci1yYWRpdXM6IDJweCIKICBzdHJva2Utd2lkdGg9IjIiCiAgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIgogIHN0cm9rZS1saW5lam9pbj0icm91bmQiCj4KICA8cGF0aCBkPSJNNSAxMmgxNCIgLz4KICA8cGF0aCBkPSJtMTIgNSA3IDctNyA3IiAvPgo8L3N2Zz4K) - https://lucide.dev/icons/arrow-right
		* @see https://lucide.dev/guide/packages/lucide-svelte - Documentation
		*
		* @param {Object} props - Lucide icons props and any valid SVG attribute
		* @returns {FunctionalComponent} Svelte component
		*
		*/
		Icon($$anchor, spread_props({ name: "arrow-right" }, () => $$sanitized_props, {
			get iconNode() {
				return iconNode;
			},
			children: ($$anchor, $$slotProps) => {
				var fragment_1 = comment();
				slot(first_child(fragment_1), $$props, "default", {}, null);
				append($$anchor, fragment_1);
			},
			$$slots: { default: true }
		}));
	}
	//#endregion
	//#region node_modules/lucide-svelte/dist/icons/circle-check.svelte
	function Circle_check($$anchor, $$props) {
		const $$sanitized_props = legacy_rest_props($$props, [
			"children",
			"$$slots",
			"$$events",
			"$$legacy"
		]);
		/**
		* @license lucide-svelte v1.0.1 - ISC
		*
		* ISC License
		*
		* Copyright (c) 2026 Lucide Icons and Contributors
		*
		* Permission to use, copy, modify, and/or distribute this software for any
		* purpose with or without fee is hereby granted, provided that the above
		* copyright notice and this permission notice appear in all copies.
		*
		* THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
		* WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
		* MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
		* ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
		* WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
		* ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
		* OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
		*
		* ---
		*
		* The following Lucide icons are derived from the Feather project:
		*
		* airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
		*
		* The MIT License (MIT) (for the icons listed above)
		*
		* Copyright (c) 2013-present Cole Bemis
		*
		* Permission is hereby granted, free of charge, to any person obtaining a copy
		* of this software and associated documentation files (the "Software"), to deal
		* in the Software without restriction, including without limitation the rights
		* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
		* copies of the Software, and to permit persons to whom the Software is
		* furnished to do so, subject to the following conditions:
		*
		* The above copyright notice and this permission notice shall be included in all
		* copies or substantial portions of the Software.
		*
		* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
		* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
		* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
		* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
		* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
		* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
		* SOFTWARE.
		*
		*/
		const iconNode = [["circle", {
			"cx": "12",
			"cy": "12",
			"r": "10"
		}], ["path", { "d": "m9 12 2 2 4-4" }]];
		/**
		* @component @name CircleCheck
		* @description Lucide SVG icon component, renders SVG Element with children.
		*
		* @preview ![img](data:image/svg+xml;base64,PHN2ZyAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogIHdpZHRoPSIyNCIKICBoZWlnaHQ9IjI0IgogIHZpZXdCb3g9IjAgMCAyNCAyNCIKICBmaWxsPSJub25lIgogIHN0cm9rZT0iIzAwMCIgc3R5bGU9ImJhY2tncm91bmQtY29sb3I6ICNmZmY7IGJvcmRlci1yYWRpdXM6IDJweCIKICBzdHJva2Utd2lkdGg9IjIiCiAgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIgogIHN0cm9rZS1saW5lam9pbj0icm91bmQiCj4KICA8Y2lyY2xlIGN4PSIxMiIgY3k9IjEyIiByPSIxMCIgLz4KICA8cGF0aCBkPSJtOSAxMiAyIDIgNC00IiAvPgo8L3N2Zz4K) - https://lucide.dev/icons/circle-check
		* @see https://lucide.dev/guide/packages/lucide-svelte - Documentation
		*
		* @param {Object} props - Lucide icons props and any valid SVG attribute
		* @returns {FunctionalComponent} Svelte component
		*
		*/
		Icon($$anchor, spread_props({ name: "circle-check" }, () => $$sanitized_props, {
			get iconNode() {
				return iconNode;
			},
			children: ($$anchor, $$slotProps) => {
				var fragment_1 = comment();
				slot(first_child(fragment_1), $$props, "default", {}, null);
				append($$anchor, fragment_1);
			},
			$$slots: { default: true }
		}));
	}
	//#endregion
	//#region node_modules/lucide-svelte/dist/icons/circle.svelte
	function Circle($$anchor, $$props) {
		const $$sanitized_props = legacy_rest_props($$props, [
			"children",
			"$$slots",
			"$$events",
			"$$legacy"
		]);
		/**
		* @license lucide-svelte v1.0.1 - ISC
		*
		* ISC License
		*
		* Copyright (c) 2026 Lucide Icons and Contributors
		*
		* Permission to use, copy, modify, and/or distribute this software for any
		* purpose with or without fee is hereby granted, provided that the above
		* copyright notice and this permission notice appear in all copies.
		*
		* THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
		* WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
		* MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
		* ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
		* WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
		* ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
		* OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
		*
		* ---
		*
		* The following Lucide icons are derived from the Feather project:
		*
		* airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
		*
		* The MIT License (MIT) (for the icons listed above)
		*
		* Copyright (c) 2013-present Cole Bemis
		*
		* Permission is hereby granted, free of charge, to any person obtaining a copy
		* of this software and associated documentation files (the "Software"), to deal
		* in the Software without restriction, including without limitation the rights
		* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
		* copies of the Software, and to permit persons to whom the Software is
		* furnished to do so, subject to the following conditions:
		*
		* The above copyright notice and this permission notice shall be included in all
		* copies or substantial portions of the Software.
		*
		* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
		* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
		* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
		* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
		* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
		* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
		* SOFTWARE.
		*
		*/
		const iconNode = [["circle", {
			"cx": "12",
			"cy": "12",
			"r": "10"
		}]];
		/**
		* @component @name Circle
		* @description Lucide SVG icon component, renders SVG Element with children.
		*
		* @preview ![img](data:image/svg+xml;base64,PHN2ZyAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogIHdpZHRoPSIyNCIKICBoZWlnaHQ9IjI0IgogIHZpZXdCb3g9IjAgMCAyNCAyNCIKICBmaWxsPSJub25lIgogIHN0cm9rZT0iIzAwMCIgc3R5bGU9ImJhY2tncm91bmQtY29sb3I6ICNmZmY7IGJvcmRlci1yYWRpdXM6IDJweCIKICBzdHJva2Utd2lkdGg9IjIiCiAgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIgogIHN0cm9rZS1saW5lam9pbj0icm91bmQiCj4KICA8Y2lyY2xlIGN4PSIxMiIgY3k9IjEyIiByPSIxMCIgLz4KPC9zdmc+Cg==) - https://lucide.dev/icons/circle
		* @see https://lucide.dev/guide/packages/lucide-svelte - Documentation
		*
		* @param {Object} props - Lucide icons props and any valid SVG attribute
		* @returns {FunctionalComponent} Svelte component
		*
		*/
		Icon($$anchor, spread_props({ name: "circle" }, () => $$sanitized_props, {
			get iconNode() {
				return iconNode;
			},
			children: ($$anchor, $$slotProps) => {
				var fragment_1 = comment();
				slot(first_child(fragment_1), $$props, "default", {}, null);
				append($$anchor, fragment_1);
			},
			$$slots: { default: true }
		}));
	}
	//#endregion
	//#region node_modules/lucide-svelte/dist/icons/copy.svelte
	function Copy($$anchor, $$props) {
		const $$sanitized_props = legacy_rest_props($$props, [
			"children",
			"$$slots",
			"$$events",
			"$$legacy"
		]);
		/**
		* @license lucide-svelte v1.0.1 - ISC
		*
		* ISC License
		*
		* Copyright (c) 2026 Lucide Icons and Contributors
		*
		* Permission to use, copy, modify, and/or distribute this software for any
		* purpose with or without fee is hereby granted, provided that the above
		* copyright notice and this permission notice appear in all copies.
		*
		* THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
		* WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
		* MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
		* ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
		* WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
		* ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
		* OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
		*
		* ---
		*
		* The following Lucide icons are derived from the Feather project:
		*
		* airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
		*
		* The MIT License (MIT) (for the icons listed above)
		*
		* Copyright (c) 2013-present Cole Bemis
		*
		* Permission is hereby granted, free of charge, to any person obtaining a copy
		* of this software and associated documentation files (the "Software"), to deal
		* in the Software without restriction, including without limitation the rights
		* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
		* copies of the Software, and to permit persons to whom the Software is
		* furnished to do so, subject to the following conditions:
		*
		* The above copyright notice and this permission notice shall be included in all
		* copies or substantial portions of the Software.
		*
		* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
		* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
		* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
		* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
		* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
		* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
		* SOFTWARE.
		*
		*/
		const iconNode = [["rect", {
			"width": "14",
			"height": "14",
			"x": "8",
			"y": "8",
			"rx": "2",
			"ry": "2"
		}], ["path", { "d": "M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" }]];
		/**
		* @component @name Copy
		* @description Lucide SVG icon component, renders SVG Element with children.
		*
		* @preview ![img](data:image/svg+xml;base64,PHN2ZyAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogIHdpZHRoPSIyNCIKICBoZWlnaHQ9IjI0IgogIHZpZXdCb3g9IjAgMCAyNCAyNCIKICBmaWxsPSJub25lIgogIHN0cm9rZT0iIzAwMCIgc3R5bGU9ImJhY2tncm91bmQtY29sb3I6ICNmZmY7IGJvcmRlci1yYWRpdXM6IDJweCIKICBzdHJva2Utd2lkdGg9IjIiCiAgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIgogIHN0cm9rZS1saW5lam9pbj0icm91bmQiCj4KICA8cmVjdCB3aWR0aD0iMTQiIGhlaWdodD0iMTQiIHg9IjgiIHk9IjgiIHJ4PSIyIiByeT0iMiIgLz4KICA8cGF0aCBkPSJNNCAxNmMtMS4xIDAtMi0uOS0yLTJWNGMwLTEuMS45LTIgMi0yaDEwYzEuMSAwIDIgLjkgMiAyIiAvPgo8L3N2Zz4K) - https://lucide.dev/icons/copy
		* @see https://lucide.dev/guide/packages/lucide-svelte - Documentation
		*
		* @param {Object} props - Lucide icons props and any valid SVG attribute
		* @returns {FunctionalComponent} Svelte component
		*
		*/
		Icon($$anchor, spread_props({ name: "copy" }, () => $$sanitized_props, {
			get iconNode() {
				return iconNode;
			},
			children: ($$anchor, $$slotProps) => {
				var fragment_1 = comment();
				slot(first_child(fragment_1), $$props, "default", {}, null);
				append($$anchor, fragment_1);
			},
			$$slots: { default: true }
		}));
	}
	//#endregion
	//#region node_modules/lucide-svelte/dist/icons/credit-card.svelte
	function Credit_card($$anchor, $$props) {
		const $$sanitized_props = legacy_rest_props($$props, [
			"children",
			"$$slots",
			"$$events",
			"$$legacy"
		]);
		/**
		* @license lucide-svelte v1.0.1 - ISC
		*
		* ISC License
		*
		* Copyright (c) 2026 Lucide Icons and Contributors
		*
		* Permission to use, copy, modify, and/or distribute this software for any
		* purpose with or without fee is hereby granted, provided that the above
		* copyright notice and this permission notice appear in all copies.
		*
		* THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
		* WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
		* MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
		* ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
		* WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
		* ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
		* OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
		*
		* ---
		*
		* The following Lucide icons are derived from the Feather project:
		*
		* airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
		*
		* The MIT License (MIT) (for the icons listed above)
		*
		* Copyright (c) 2013-present Cole Bemis
		*
		* Permission is hereby granted, free of charge, to any person obtaining a copy
		* of this software and associated documentation files (the "Software"), to deal
		* in the Software without restriction, including without limitation the rights
		* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
		* copies of the Software, and to permit persons to whom the Software is
		* furnished to do so, subject to the following conditions:
		*
		* The above copyright notice and this permission notice shall be included in all
		* copies or substantial portions of the Software.
		*
		* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
		* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
		* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
		* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
		* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
		* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
		* SOFTWARE.
		*
		*/
		const iconNode = [["rect", {
			"width": "20",
			"height": "14",
			"x": "2",
			"y": "5",
			"rx": "2"
		}], ["line", {
			"x1": "2",
			"x2": "22",
			"y1": "10",
			"y2": "10"
		}]];
		/**
		* @component @name CreditCard
		* @description Lucide SVG icon component, renders SVG Element with children.
		*
		* @preview ![img](data:image/svg+xml;base64,PHN2ZyAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogIHdpZHRoPSIyNCIKICBoZWlnaHQ9IjI0IgogIHZpZXdCb3g9IjAgMCAyNCAyNCIKICBmaWxsPSJub25lIgogIHN0cm9rZT0iIzAwMCIgc3R5bGU9ImJhY2tncm91bmQtY29sb3I6ICNmZmY7IGJvcmRlci1yYWRpdXM6IDJweCIKICBzdHJva2Utd2lkdGg9IjIiCiAgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIgogIHN0cm9rZS1saW5lam9pbj0icm91bmQiCj4KICA8cmVjdCB3aWR0aD0iMjAiIGhlaWdodD0iMTQiIHg9IjIiIHk9IjUiIHJ4PSIyIiAvPgogIDxsaW5lIHgxPSIyIiB4Mj0iMjIiIHkxPSIxMCIgeTI9IjEwIiAvPgo8L3N2Zz4K) - https://lucide.dev/icons/credit-card
		* @see https://lucide.dev/guide/packages/lucide-svelte - Documentation
		*
		* @param {Object} props - Lucide icons props and any valid SVG attribute
		* @returns {FunctionalComponent} Svelte component
		*
		*/
		Icon($$anchor, spread_props({ name: "credit-card" }, () => $$sanitized_props, {
			get iconNode() {
				return iconNode;
			},
			children: ($$anchor, $$slotProps) => {
				var fragment_1 = comment();
				slot(first_child(fragment_1), $$props, "default", {}, null);
				append($$anchor, fragment_1);
			},
			$$slots: { default: true }
		}));
	}
	//#endregion
	//#region node_modules/lucide-svelte/dist/icons/crown.svelte
	function Crown($$anchor, $$props) {
		const $$sanitized_props = legacy_rest_props($$props, [
			"children",
			"$$slots",
			"$$events",
			"$$legacy"
		]);
		/**
		* @license lucide-svelte v1.0.1 - ISC
		*
		* ISC License
		*
		* Copyright (c) 2026 Lucide Icons and Contributors
		*
		* Permission to use, copy, modify, and/or distribute this software for any
		* purpose with or without fee is hereby granted, provided that the above
		* copyright notice and this permission notice appear in all copies.
		*
		* THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
		* WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
		* MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
		* ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
		* WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
		* ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
		* OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
		*
		* ---
		*
		* The following Lucide icons are derived from the Feather project:
		*
		* airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
		*
		* The MIT License (MIT) (for the icons listed above)
		*
		* Copyright (c) 2013-present Cole Bemis
		*
		* Permission is hereby granted, free of charge, to any person obtaining a copy
		* of this software and associated documentation files (the "Software"), to deal
		* in the Software without restriction, including without limitation the rights
		* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
		* copies of the Software, and to permit persons to whom the Software is
		* furnished to do so, subject to the following conditions:
		*
		* The above copyright notice and this permission notice shall be included in all
		* copies or substantial portions of the Software.
		*
		* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
		* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
		* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
		* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
		* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
		* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
		* SOFTWARE.
		*
		*/
		const iconNode = [["path", { "d": "M11.562 3.266a.5.5 0 0 1 .876 0L15.39 8.87a1 1 0 0 0 1.516.294L21.183 5.5a.5.5 0 0 1 .798.519l-2.834 10.246a1 1 0 0 1-.956.734H5.81a1 1 0 0 1-.957-.734L2.02 6.02a.5.5 0 0 1 .798-.519l4.276 3.664a1 1 0 0 0 1.516-.294z" }], ["path", { "d": "M5 21h14" }]];
		/**
		* @component @name Crown
		* @description Lucide SVG icon component, renders SVG Element with children.
		*
		* @preview ![img](data:image/svg+xml;base64,PHN2ZyAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogIHdpZHRoPSIyNCIKICBoZWlnaHQ9IjI0IgogIHZpZXdCb3g9IjAgMCAyNCAyNCIKICBmaWxsPSJub25lIgogIHN0cm9rZT0iIzAwMCIgc3R5bGU9ImJhY2tncm91bmQtY29sb3I6ICNmZmY7IGJvcmRlci1yYWRpdXM6IDJweCIKICBzdHJva2Utd2lkdGg9IjIiCiAgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIgogIHN0cm9rZS1saW5lam9pbj0icm91bmQiCj4KICA8cGF0aCBkPSJNMTEuNTYyIDMuMjY2YS41LjUgMCAwIDEgLjg3NiAwTDE1LjM5IDguODdhMSAxIDAgMCAwIDEuNTE2LjI5NEwyMS4xODMgNS41YS41LjUgMCAwIDEgLjc5OC41MTlsLTIuODM0IDEwLjI0NmExIDEgMCAwIDEtLjk1Ni43MzRINS44MWExIDEgMCAwIDEtLjk1Ny0uNzM0TDIuMDIgNi4wMmEuNS41IDAgMCAxIC43OTgtLjUxOWw0LjI3NiAzLjY2NGExIDEgMCAwIDAgMS41MTYtLjI5NHoiIC8+CiAgPHBhdGggZD0iTTUgMjFoMTQiIC8+Cjwvc3ZnPgo=) - https://lucide.dev/icons/crown
		* @see https://lucide.dev/guide/packages/lucide-svelte - Documentation
		*
		* @param {Object} props - Lucide icons props and any valid SVG attribute
		* @returns {FunctionalComponent} Svelte component
		*
		*/
		Icon($$anchor, spread_props({ name: "crown" }, () => $$sanitized_props, {
			get iconNode() {
				return iconNode;
			},
			children: ($$anchor, $$slotProps) => {
				var fragment_1 = comment();
				slot(first_child(fragment_1), $$props, "default", {}, null);
				append($$anchor, fragment_1);
			},
			$$slots: { default: true }
		}));
	}
	//#endregion
	//#region node_modules/lucide-svelte/dist/icons/database.svelte
	function Database($$anchor, $$props) {
		const $$sanitized_props = legacy_rest_props($$props, [
			"children",
			"$$slots",
			"$$events",
			"$$legacy"
		]);
		/**
		* @license lucide-svelte v1.0.1 - ISC
		*
		* ISC License
		*
		* Copyright (c) 2026 Lucide Icons and Contributors
		*
		* Permission to use, copy, modify, and/or distribute this software for any
		* purpose with or without fee is hereby granted, provided that the above
		* copyright notice and this permission notice appear in all copies.
		*
		* THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
		* WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
		* MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
		* ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
		* WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
		* ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
		* OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
		*
		* ---
		*
		* The following Lucide icons are derived from the Feather project:
		*
		* airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
		*
		* The MIT License (MIT) (for the icons listed above)
		*
		* Copyright (c) 2013-present Cole Bemis
		*
		* Permission is hereby granted, free of charge, to any person obtaining a copy
		* of this software and associated documentation files (the "Software"), to deal
		* in the Software without restriction, including without limitation the rights
		* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
		* copies of the Software, and to permit persons to whom the Software is
		* furnished to do so, subject to the following conditions:
		*
		* The above copyright notice and this permission notice shall be included in all
		* copies or substantial portions of the Software.
		*
		* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
		* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
		* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
		* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
		* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
		* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
		* SOFTWARE.
		*
		*/
		const iconNode = [
			["ellipse", {
				"cx": "12",
				"cy": "5",
				"rx": "9",
				"ry": "3"
			}],
			["path", { "d": "M3 5V19A9 3 0 0 0 21 19V5" }],
			["path", { "d": "M3 12A9 3 0 0 0 21 12" }]
		];
		/**
		* @component @name Database
		* @description Lucide SVG icon component, renders SVG Element with children.
		*
		* @preview ![img](data:image/svg+xml;base64,PHN2ZyAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogIHdpZHRoPSIyNCIKICBoZWlnaHQ9IjI0IgogIHZpZXdCb3g9IjAgMCAyNCAyNCIKICBmaWxsPSJub25lIgogIHN0cm9rZT0iIzAwMCIgc3R5bGU9ImJhY2tncm91bmQtY29sb3I6ICNmZmY7IGJvcmRlci1yYWRpdXM6IDJweCIKICBzdHJva2Utd2lkdGg9IjIiCiAgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIgogIHN0cm9rZS1saW5lam9pbj0icm91bmQiCj4KICA8ZWxsaXBzZSBjeD0iMTIiIGN5PSI1IiByeD0iOSIgcnk9IjMiIC8+CiAgPHBhdGggZD0iTTMgNVYxOUE5IDMgMCAwIDAgMjEgMTlWNSIgLz4KICA8cGF0aCBkPSJNMyAxMkE5IDMgMCAwIDAgMjEgMTIiIC8+Cjwvc3ZnPgo=) - https://lucide.dev/icons/database
		* @see https://lucide.dev/guide/packages/lucide-svelte - Documentation
		*
		* @param {Object} props - Lucide icons props and any valid SVG attribute
		* @returns {FunctionalComponent} Svelte component
		*
		*/
		Icon($$anchor, spread_props({ name: "database" }, () => $$sanitized_props, {
			get iconNode() {
				return iconNode;
			},
			children: ($$anchor, $$slotProps) => {
				var fragment_1 = comment();
				slot(first_child(fragment_1), $$props, "default", {}, null);
				append($$anchor, fragment_1);
			},
			$$slots: { default: true }
		}));
	}
	//#endregion
	//#region node_modules/lucide-svelte/dist/icons/download.svelte
	function Download($$anchor, $$props) {
		const $$sanitized_props = legacy_rest_props($$props, [
			"children",
			"$$slots",
			"$$events",
			"$$legacy"
		]);
		/**
		* @license lucide-svelte v1.0.1 - ISC
		*
		* ISC License
		*
		* Copyright (c) 2026 Lucide Icons and Contributors
		*
		* Permission to use, copy, modify, and/or distribute this software for any
		* purpose with or without fee is hereby granted, provided that the above
		* copyright notice and this permission notice appear in all copies.
		*
		* THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
		* WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
		* MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
		* ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
		* WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
		* ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
		* OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
		*
		* ---
		*
		* The following Lucide icons are derived from the Feather project:
		*
		* airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
		*
		* The MIT License (MIT) (for the icons listed above)
		*
		* Copyright (c) 2013-present Cole Bemis
		*
		* Permission is hereby granted, free of charge, to any person obtaining a copy
		* of this software and associated documentation files (the "Software"), to deal
		* in the Software without restriction, including without limitation the rights
		* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
		* copies of the Software, and to permit persons to whom the Software is
		* furnished to do so, subject to the following conditions:
		*
		* The above copyright notice and this permission notice shall be included in all
		* copies or substantial portions of the Software.
		*
		* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
		* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
		* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
		* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
		* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
		* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
		* SOFTWARE.
		*
		*/
		const iconNode = [
			["path", { "d": "M12 15V3" }],
			["path", { "d": "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" }],
			["path", { "d": "m7 10 5 5 5-5" }]
		];
		/**
		* @component @name Download
		* @description Lucide SVG icon component, renders SVG Element with children.
		*
		* @preview ![img](data:image/svg+xml;base64,PHN2ZyAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogIHdpZHRoPSIyNCIKICBoZWlnaHQ9IjI0IgogIHZpZXdCb3g9IjAgMCAyNCAyNCIKICBmaWxsPSJub25lIgogIHN0cm9rZT0iIzAwMCIgc3R5bGU9ImJhY2tncm91bmQtY29sb3I6ICNmZmY7IGJvcmRlci1yYWRpdXM6IDJweCIKICBzdHJva2Utd2lkdGg9IjIiCiAgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIgogIHN0cm9rZS1saW5lam9pbj0icm91bmQiCj4KICA8cGF0aCBkPSJNMTIgMTVWMyIgLz4KICA8cGF0aCBkPSJNMjEgMTV2NGEyIDIgMCAwIDEtMiAySDVhMiAyIDAgMCAxLTItMnYtNCIgLz4KICA8cGF0aCBkPSJtNyAxMCA1IDUgNS01IiAvPgo8L3N2Zz4K) - https://lucide.dev/icons/download
		* @see https://lucide.dev/guide/packages/lucide-svelte - Documentation
		*
		* @param {Object} props - Lucide icons props and any valid SVG attribute
		* @returns {FunctionalComponent} Svelte component
		*
		*/
		Icon($$anchor, spread_props({ name: "download" }, () => $$sanitized_props, {
			get iconNode() {
				return iconNode;
			},
			children: ($$anchor, $$slotProps) => {
				var fragment_1 = comment();
				slot(first_child(fragment_1), $$props, "default", {}, null);
				append($$anchor, fragment_1);
			},
			$$slots: { default: true }
		}));
	}
	//#endregion
	//#region node_modules/lucide-svelte/dist/icons/earth.svelte
	function Earth($$anchor, $$props) {
		const $$sanitized_props = legacy_rest_props($$props, [
			"children",
			"$$slots",
			"$$events",
			"$$legacy"
		]);
		/**
		* @license lucide-svelte v1.0.1 - ISC
		*
		* ISC License
		*
		* Copyright (c) 2026 Lucide Icons and Contributors
		*
		* Permission to use, copy, modify, and/or distribute this software for any
		* purpose with or without fee is hereby granted, provided that the above
		* copyright notice and this permission notice appear in all copies.
		*
		* THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
		* WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
		* MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
		* ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
		* WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
		* ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
		* OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
		*
		* ---
		*
		* The following Lucide icons are derived from the Feather project:
		*
		* airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
		*
		* The MIT License (MIT) (for the icons listed above)
		*
		* Copyright (c) 2013-present Cole Bemis
		*
		* Permission is hereby granted, free of charge, to any person obtaining a copy
		* of this software and associated documentation files (the "Software"), to deal
		* in the Software without restriction, including without limitation the rights
		* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
		* copies of the Software, and to permit persons to whom the Software is
		* furnished to do so, subject to the following conditions:
		*
		* The above copyright notice and this permission notice shall be included in all
		* copies or substantial portions of the Software.
		*
		* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
		* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
		* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
		* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
		* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
		* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
		* SOFTWARE.
		*
		*/
		const iconNode = [
			["path", { "d": "M21.54 15H17a2 2 0 0 0-2 2v4.54" }],
			["path", { "d": "M7 3.34V5a3 3 0 0 0 3 3a2 2 0 0 1 2 2c0 1.1.9 2 2 2a2 2 0 0 0 2-2c0-1.1.9-2 2-2h3.17" }],
			["path", { "d": "M11 21.95V18a2 2 0 0 0-2-2a2 2 0 0 1-2-2v-1a2 2 0 0 0-2-2H2.05" }],
			["circle", {
				"cx": "12",
				"cy": "12",
				"r": "10"
			}]
		];
		/**
		* @component @name Earth
		* @description Lucide SVG icon component, renders SVG Element with children.
		*
		* @preview ![img](data:image/svg+xml;base64,PHN2ZyAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogIHdpZHRoPSIyNCIKICBoZWlnaHQ9IjI0IgogIHZpZXdCb3g9IjAgMCAyNCAyNCIKICBmaWxsPSJub25lIgogIHN0cm9rZT0iIzAwMCIgc3R5bGU9ImJhY2tncm91bmQtY29sb3I6ICNmZmY7IGJvcmRlci1yYWRpdXM6IDJweCIKICBzdHJva2Utd2lkdGg9IjIiCiAgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIgogIHN0cm9rZS1saW5lam9pbj0icm91bmQiCj4KICA8cGF0aCBkPSJNMjEuNTQgMTVIMTdhMiAyIDAgMCAwLTIgMnY0LjU0IiAvPgogIDxwYXRoIGQ9Ik03IDMuMzRWNWEzIDMgMCAwIDAgMyAzYTIgMiAwIDAgMSAyIDJjMCAxLjEuOSAyIDIgMmEyIDIgMCAwIDAgMi0yYzAtMS4xLjktMiAyLTJoMy4xNyIgLz4KICA8cGF0aCBkPSJNMTEgMjEuOTVWMThhMiAyIDAgMCAwLTItMmEyIDIgMCAwIDEtMi0ydi0xYTIgMiAwIDAgMC0yLTJIMi4wNSIgLz4KICA8Y2lyY2xlIGN4PSIxMiIgY3k9IjEyIiByPSIxMCIgLz4KPC9zdmc+Cg==) - https://lucide.dev/icons/earth
		* @see https://lucide.dev/guide/packages/lucide-svelte - Documentation
		*
		* @param {Object} props - Lucide icons props and any valid SVG attribute
		* @returns {FunctionalComponent} Svelte component
		*
		*/
		Icon($$anchor, spread_props({ name: "earth" }, () => $$sanitized_props, {
			get iconNode() {
				return iconNode;
			},
			children: ($$anchor, $$slotProps) => {
				var fragment_1 = comment();
				slot(first_child(fragment_1), $$props, "default", {}, null);
				append($$anchor, fragment_1);
			},
			$$slots: { default: true }
		}));
	}
	//#endregion
	//#region node_modules/lucide-svelte/dist/icons/gift.svelte
	function Gift($$anchor, $$props) {
		const $$sanitized_props = legacy_rest_props($$props, [
			"children",
			"$$slots",
			"$$events",
			"$$legacy"
		]);
		/**
		* @license lucide-svelte v1.0.1 - ISC
		*
		* ISC License
		*
		* Copyright (c) 2026 Lucide Icons and Contributors
		*
		* Permission to use, copy, modify, and/or distribute this software for any
		* purpose with or without fee is hereby granted, provided that the above
		* copyright notice and this permission notice appear in all copies.
		*
		* THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
		* WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
		* MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
		* ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
		* WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
		* ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
		* OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
		*
		* ---
		*
		* The following Lucide icons are derived from the Feather project:
		*
		* airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
		*
		* The MIT License (MIT) (for the icons listed above)
		*
		* Copyright (c) 2013-present Cole Bemis
		*
		* Permission is hereby granted, free of charge, to any person obtaining a copy
		* of this software and associated documentation files (the "Software"), to deal
		* in the Software without restriction, including without limitation the rights
		* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
		* copies of the Software, and to permit persons to whom the Software is
		* furnished to do so, subject to the following conditions:
		*
		* The above copyright notice and this permission notice shall be included in all
		* copies or substantial portions of the Software.
		*
		* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
		* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
		* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
		* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
		* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
		* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
		* SOFTWARE.
		*
		*/
		const iconNode = [
			["path", { "d": "M12 7v14" }],
			["path", { "d": "M20 11v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-8" }],
			["path", { "d": "M7.5 7a1 1 0 0 1 0-5A4.8 8 0 0 1 12 7a4.8 8 0 0 1 4.5-5 1 1 0 0 1 0 5" }],
			["rect", {
				"x": "3",
				"y": "7",
				"width": "18",
				"height": "4",
				"rx": "1"
			}]
		];
		/**
		* @component @name Gift
		* @description Lucide SVG icon component, renders SVG Element with children.
		*
		* @preview ![img](data:image/svg+xml;base64,PHN2ZyAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogIHdpZHRoPSIyNCIKICBoZWlnaHQ9IjI0IgogIHZpZXdCb3g9IjAgMCAyNCAyNCIKICBmaWxsPSJub25lIgogIHN0cm9rZT0iIzAwMCIgc3R5bGU9ImJhY2tncm91bmQtY29sb3I6ICNmZmY7IGJvcmRlci1yYWRpdXM6IDJweCIKICBzdHJva2Utd2lkdGg9IjIiCiAgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIgogIHN0cm9rZS1saW5lam9pbj0icm91bmQiCj4KICA8cGF0aCBkPSJNMTIgN3YxNCIgLz4KICA8cGF0aCBkPSJNMjAgMTF2OGEyIDIgMCAwIDEtMiAySDZhMiAyIDAgMCAxLTItMnYtOCIgLz4KICA8cGF0aCBkPSJNNy41IDdhMSAxIDAgMCAxIDAtNUE0LjggOCAwIDAgMSAxMiA3YTQuOCA4IDAgMCAxIDQuNS01IDEgMSAwIDAgMSAwIDUiIC8+CiAgPHJlY3QgeD0iMyIgeT0iNyIgd2lkdGg9IjE4IiBoZWlnaHQ9IjQiIHJ4PSIxIiAvPgo8L3N2Zz4K) - https://lucide.dev/icons/gift
		* @see https://lucide.dev/guide/packages/lucide-svelte - Documentation
		*
		* @param {Object} props - Lucide icons props and any valid SVG attribute
		* @returns {FunctionalComponent} Svelte component
		*
		*/
		Icon($$anchor, spread_props({ name: "gift" }, () => $$sanitized_props, {
			get iconNode() {
				return iconNode;
			},
			children: ($$anchor, $$slotProps) => {
				var fragment_1 = comment();
				slot(first_child(fragment_1), $$props, "default", {}, null);
				append($$anchor, fragment_1);
			},
			$$slots: { default: true }
		}));
	}
	//#endregion
	//#region node_modules/lucide-svelte/dist/icons/house.svelte
	function House($$anchor, $$props) {
		const $$sanitized_props = legacy_rest_props($$props, [
			"children",
			"$$slots",
			"$$events",
			"$$legacy"
		]);
		/**
		* @license lucide-svelte v1.0.1 - ISC
		*
		* ISC License
		*
		* Copyright (c) 2026 Lucide Icons and Contributors
		*
		* Permission to use, copy, modify, and/or distribute this software for any
		* purpose with or without fee is hereby granted, provided that the above
		* copyright notice and this permission notice appear in all copies.
		*
		* THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
		* WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
		* MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
		* ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
		* WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
		* ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
		* OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
		*
		* ---
		*
		* The following Lucide icons are derived from the Feather project:
		*
		* airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
		*
		* The MIT License (MIT) (for the icons listed above)
		*
		* Copyright (c) 2013-present Cole Bemis
		*
		* Permission is hereby granted, free of charge, to any person obtaining a copy
		* of this software and associated documentation files (the "Software"), to deal
		* in the Software without restriction, including without limitation the rights
		* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
		* copies of the Software, and to permit persons to whom the Software is
		* furnished to do so, subject to the following conditions:
		*
		* The above copyright notice and this permission notice shall be included in all
		* copies or substantial portions of the Software.
		*
		* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
		* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
		* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
		* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
		* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
		* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
		* SOFTWARE.
		*
		*/
		const iconNode = [["path", { "d": "M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8" }], ["path", { "d": "M3 10a2 2 0 0 1 .709-1.528l7-6a2 2 0 0 1 2.582 0l7 6A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" }]];
		/**
		* @component @name House
		* @description Lucide SVG icon component, renders SVG Element with children.
		*
		* @preview ![img](data:image/svg+xml;base64,PHN2ZyAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogIHdpZHRoPSIyNCIKICBoZWlnaHQ9IjI0IgogIHZpZXdCb3g9IjAgMCAyNCAyNCIKICBmaWxsPSJub25lIgogIHN0cm9rZT0iIzAwMCIgc3R5bGU9ImJhY2tncm91bmQtY29sb3I6ICNmZmY7IGJvcmRlci1yYWRpdXM6IDJweCIKICBzdHJva2Utd2lkdGg9IjIiCiAgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIgogIHN0cm9rZS1saW5lam9pbj0icm91bmQiCj4KICA8cGF0aCBkPSJNMTUgMjF2LThhMSAxIDAgMCAwLTEtMWgtNGExIDEgMCAwIDAtMSAxdjgiIC8+CiAgPHBhdGggZD0iTTMgMTBhMiAyIDAgMCAxIC43MDktMS41MjhsNy02YTIgMiAwIDAgMSAyLjU4MiAwbDcgNkEyIDIgMCAwIDEgMjEgMTB2OWEyIDIgMCAwIDEtMiAySDVhMiAyIDAgMCAxLTItMnoiIC8+Cjwvc3ZnPgo=) - https://lucide.dev/icons/house
		* @see https://lucide.dev/guide/packages/lucide-svelte - Documentation
		*
		* @param {Object} props - Lucide icons props and any valid SVG attribute
		* @returns {FunctionalComponent} Svelte component
		*
		*/
		Icon($$anchor, spread_props({ name: "house" }, () => $$sanitized_props, {
			get iconNode() {
				return iconNode;
			},
			children: ($$anchor, $$slotProps) => {
				var fragment_1 = comment();
				slot(first_child(fragment_1), $$props, "default", {}, null);
				append($$anchor, fragment_1);
			},
			$$slots: { default: true }
		}));
	}
	//#endregion
	//#region node_modules/lucide-svelte/dist/icons/lock-keyhole.svelte
	function Lock_keyhole($$anchor, $$props) {
		const $$sanitized_props = legacy_rest_props($$props, [
			"children",
			"$$slots",
			"$$events",
			"$$legacy"
		]);
		/**
		* @license lucide-svelte v1.0.1 - ISC
		*
		* ISC License
		*
		* Copyright (c) 2026 Lucide Icons and Contributors
		*
		* Permission to use, copy, modify, and/or distribute this software for any
		* purpose with or without fee is hereby granted, provided that the above
		* copyright notice and this permission notice appear in all copies.
		*
		* THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
		* WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
		* MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
		* ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
		* WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
		* ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
		* OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
		*
		* ---
		*
		* The following Lucide icons are derived from the Feather project:
		*
		* airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
		*
		* The MIT License (MIT) (for the icons listed above)
		*
		* Copyright (c) 2013-present Cole Bemis
		*
		* Permission is hereby granted, free of charge, to any person obtaining a copy
		* of this software and associated documentation files (the "Software"), to deal
		* in the Software without restriction, including without limitation the rights
		* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
		* copies of the Software, and to permit persons to whom the Software is
		* furnished to do so, subject to the following conditions:
		*
		* The above copyright notice and this permission notice shall be included in all
		* copies or substantial portions of the Software.
		*
		* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
		* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
		* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
		* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
		* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
		* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
		* SOFTWARE.
		*
		*/
		const iconNode = [
			["circle", {
				"cx": "12",
				"cy": "16",
				"r": "1"
			}],
			["rect", {
				"x": "3",
				"y": "10",
				"width": "18",
				"height": "12",
				"rx": "2"
			}],
			["path", { "d": "M7 10V7a5 5 0 0 1 10 0v3" }]
		];
		/**
		* @component @name LockKeyhole
		* @description Lucide SVG icon component, renders SVG Element with children.
		*
		* @preview ![img](data:image/svg+xml;base64,PHN2ZyAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogIHdpZHRoPSIyNCIKICBoZWlnaHQ9IjI0IgogIHZpZXdCb3g9IjAgMCAyNCAyNCIKICBmaWxsPSJub25lIgogIHN0cm9rZT0iIzAwMCIgc3R5bGU9ImJhY2tncm91bmQtY29sb3I6ICNmZmY7IGJvcmRlci1yYWRpdXM6IDJweCIKICBzdHJva2Utd2lkdGg9IjIiCiAgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIgogIHN0cm9rZS1saW5lam9pbj0icm91bmQiCj4KICA8Y2lyY2xlIGN4PSIxMiIgY3k9IjE2IiByPSIxIiAvPgogIDxyZWN0IHg9IjMiIHk9IjEwIiB3aWR0aD0iMTgiIGhlaWdodD0iMTIiIHJ4PSIyIiAvPgogIDxwYXRoIGQ9Ik03IDEwVjdhNSA1IDAgMCAxIDEwIDB2MyIgLz4KPC9zdmc+Cg==) - https://lucide.dev/icons/lock-keyhole
		* @see https://lucide.dev/guide/packages/lucide-svelte - Documentation
		*
		* @param {Object} props - Lucide icons props and any valid SVG attribute
		* @returns {FunctionalComponent} Svelte component
		*
		*/
		Icon($$anchor, spread_props({ name: "lock-keyhole" }, () => $$sanitized_props, {
			get iconNode() {
				return iconNode;
			},
			children: ($$anchor, $$slotProps) => {
				var fragment_1 = comment();
				slot(first_child(fragment_1), $$props, "default", {}, null);
				append($$anchor, fragment_1);
			},
			$$slots: { default: true }
		}));
	}
	//#endregion
	//#region node_modules/lucide-svelte/dist/icons/mail.svelte
	function Mail($$anchor, $$props) {
		const $$sanitized_props = legacy_rest_props($$props, [
			"children",
			"$$slots",
			"$$events",
			"$$legacy"
		]);
		/**
		* @license lucide-svelte v1.0.1 - ISC
		*
		* ISC License
		*
		* Copyright (c) 2026 Lucide Icons and Contributors
		*
		* Permission to use, copy, modify, and/or distribute this software for any
		* purpose with or without fee is hereby granted, provided that the above
		* copyright notice and this permission notice appear in all copies.
		*
		* THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
		* WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
		* MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
		* ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
		* WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
		* ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
		* OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
		*
		* ---
		*
		* The following Lucide icons are derived from the Feather project:
		*
		* airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
		*
		* The MIT License (MIT) (for the icons listed above)
		*
		* Copyright (c) 2013-present Cole Bemis
		*
		* Permission is hereby granted, free of charge, to any person obtaining a copy
		* of this software and associated documentation files (the "Software"), to deal
		* in the Software without restriction, including without limitation the rights
		* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
		* copies of the Software, and to permit persons to whom the Software is
		* furnished to do so, subject to the following conditions:
		*
		* The above copyright notice and this permission notice shall be included in all
		* copies or substantial portions of the Software.
		*
		* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
		* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
		* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
		* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
		* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
		* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
		* SOFTWARE.
		*
		*/
		const iconNode = [["path", { "d": "m22 7-8.991 5.727a2 2 0 0 1-2.009 0L2 7" }], ["rect", {
			"x": "2",
			"y": "4",
			"width": "20",
			"height": "16",
			"rx": "2"
		}]];
		/**
		* @component @name Mail
		* @description Lucide SVG icon component, renders SVG Element with children.
		*
		* @preview ![img](data:image/svg+xml;base64,PHN2ZyAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogIHdpZHRoPSIyNCIKICBoZWlnaHQ9IjI0IgogIHZpZXdCb3g9IjAgMCAyNCAyNCIKICBmaWxsPSJub25lIgogIHN0cm9rZT0iIzAwMCIgc3R5bGU9ImJhY2tncm91bmQtY29sb3I6ICNmZmY7IGJvcmRlci1yYWRpdXM6IDJweCIKICBzdHJva2Utd2lkdGg9IjIiCiAgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIgogIHN0cm9rZS1saW5lam9pbj0icm91bmQiCj4KICA8cGF0aCBkPSJtMjIgNy04Ljk5MSA1LjcyN2EyIDIgMCAwIDEtMi4wMDkgMEwyIDciIC8+CiAgPHJlY3QgeD0iMiIgeT0iNCIgd2lkdGg9IjIwIiBoZWlnaHQ9IjE2IiByeD0iMiIgLz4KPC9zdmc+Cg==) - https://lucide.dev/icons/mail
		* @see https://lucide.dev/guide/packages/lucide-svelte - Documentation
		*
		* @param {Object} props - Lucide icons props and any valid SVG attribute
		* @returns {FunctionalComponent} Svelte component
		*
		*/
		Icon($$anchor, spread_props({ name: "mail" }, () => $$sanitized_props, {
			get iconNode() {
				return iconNode;
			},
			children: ($$anchor, $$slotProps) => {
				var fragment_1 = comment();
				slot(first_child(fragment_1), $$props, "default", {}, null);
				append($$anchor, fragment_1);
			},
			$$slots: { default: true }
		}));
	}
	//#endregion
	//#region node_modules/lucide-svelte/dist/icons/refresh-cw.svelte
	function Refresh_cw($$anchor, $$props) {
		const $$sanitized_props = legacy_rest_props($$props, [
			"children",
			"$$slots",
			"$$events",
			"$$legacy"
		]);
		/**
		* @license lucide-svelte v1.0.1 - ISC
		*
		* ISC License
		*
		* Copyright (c) 2026 Lucide Icons and Contributors
		*
		* Permission to use, copy, modify, and/or distribute this software for any
		* purpose with or without fee is hereby granted, provided that the above
		* copyright notice and this permission notice appear in all copies.
		*
		* THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
		* WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
		* MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
		* ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
		* WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
		* ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
		* OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
		*
		* ---
		*
		* The following Lucide icons are derived from the Feather project:
		*
		* airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
		*
		* The MIT License (MIT) (for the icons listed above)
		*
		* Copyright (c) 2013-present Cole Bemis
		*
		* Permission is hereby granted, free of charge, to any person obtaining a copy
		* of this software and associated documentation files (the "Software"), to deal
		* in the Software without restriction, including without limitation the rights
		* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
		* copies of the Software, and to permit persons to whom the Software is
		* furnished to do so, subject to the following conditions:
		*
		* The above copyright notice and this permission notice shall be included in all
		* copies or substantial portions of the Software.
		*
		* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
		* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
		* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
		* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
		* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
		* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
		* SOFTWARE.
		*
		*/
		const iconNode = [
			["path", { "d": "M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" }],
			["path", { "d": "M21 3v5h-5" }],
			["path", { "d": "M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" }],
			["path", { "d": "M8 16H3v5" }]
		];
		/**
		* @component @name RefreshCw
		* @description Lucide SVG icon component, renders SVG Element with children.
		*
		* @preview ![img](data:image/svg+xml;base64,PHN2ZyAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogIHdpZHRoPSIyNCIKICBoZWlnaHQ9IjI0IgogIHZpZXdCb3g9IjAgMCAyNCAyNCIKICBmaWxsPSJub25lIgogIHN0cm9rZT0iIzAwMCIgc3R5bGU9ImJhY2tncm91bmQtY29sb3I6ICNmZmY7IGJvcmRlci1yYWRpdXM6IDJweCIKICBzdHJva2Utd2lkdGg9IjIiCiAgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIgogIHN0cm9rZS1saW5lam9pbj0icm91bmQiCj4KICA8cGF0aCBkPSJNMyAxMmE5IDkgMCAwIDEgOS05IDkuNzUgOS43NSAwIDAgMSA2Ljc0IDIuNzRMMjEgOCIgLz4KICA8cGF0aCBkPSJNMjEgM3Y1aC01IiAvPgogIDxwYXRoIGQ9Ik0yMSAxMmE5IDkgMCAwIDEtOSA5IDkuNzUgOS43NSAwIDAgMS02Ljc0LTIuNzRMMyAxNiIgLz4KICA8cGF0aCBkPSJNOCAxNkgzdjUiIC8+Cjwvc3ZnPgo=) - https://lucide.dev/icons/refresh-cw
		* @see https://lucide.dev/guide/packages/lucide-svelte - Documentation
		*
		* @param {Object} props - Lucide icons props and any valid SVG attribute
		* @returns {FunctionalComponent} Svelte component
		*
		*/
		Icon($$anchor, spread_props({ name: "refresh-cw" }, () => $$sanitized_props, {
			get iconNode() {
				return iconNode;
			},
			children: ($$anchor, $$slotProps) => {
				var fragment_1 = comment();
				slot(first_child(fragment_1), $$props, "default", {}, null);
				append($$anchor, fragment_1);
			},
			$$slots: { default: true }
		}));
	}
	//#endregion
	//#region node_modules/lucide-svelte/dist/icons/repeat-2.svelte
	function Repeat_2($$anchor, $$props) {
		const $$sanitized_props = legacy_rest_props($$props, [
			"children",
			"$$slots",
			"$$events",
			"$$legacy"
		]);
		/**
		* @license lucide-svelte v1.0.1 - ISC
		*
		* ISC License
		*
		* Copyright (c) 2026 Lucide Icons and Contributors
		*
		* Permission to use, copy, modify, and/or distribute this software for any
		* purpose with or without fee is hereby granted, provided that the above
		* copyright notice and this permission notice appear in all copies.
		*
		* THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
		* WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
		* MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
		* ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
		* WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
		* ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
		* OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
		*
		* ---
		*
		* The following Lucide icons are derived from the Feather project:
		*
		* airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
		*
		* The MIT License (MIT) (for the icons listed above)
		*
		* Copyright (c) 2013-present Cole Bemis
		*
		* Permission is hereby granted, free of charge, to any person obtaining a copy
		* of this software and associated documentation files (the "Software"), to deal
		* in the Software without restriction, including without limitation the rights
		* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
		* copies of the Software, and to permit persons to whom the Software is
		* furnished to do so, subject to the following conditions:
		*
		* The above copyright notice and this permission notice shall be included in all
		* copies or substantial portions of the Software.
		*
		* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
		* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
		* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
		* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
		* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
		* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
		* SOFTWARE.
		*
		*/
		const iconNode = [
			["path", { "d": "m2 9 3-3 3 3" }],
			["path", { "d": "M13 18H7a2 2 0 0 1-2-2V6" }],
			["path", { "d": "m22 15-3 3-3-3" }],
			["path", { "d": "M11 6h6a2 2 0 0 1 2 2v10" }]
		];
		/**
		* @component @name Repeat2
		* @description Lucide SVG icon component, renders SVG Element with children.
		*
		* @preview ![img](data:image/svg+xml;base64,PHN2ZyAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogIHdpZHRoPSIyNCIKICBoZWlnaHQ9IjI0IgogIHZpZXdCb3g9IjAgMCAyNCAyNCIKICBmaWxsPSJub25lIgogIHN0cm9rZT0iIzAwMCIgc3R5bGU9ImJhY2tncm91bmQtY29sb3I6ICNmZmY7IGJvcmRlci1yYWRpdXM6IDJweCIKICBzdHJva2Utd2lkdGg9IjIiCiAgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIgogIHN0cm9rZS1saW5lam9pbj0icm91bmQiCj4KICA8cGF0aCBkPSJtMiA5IDMtMyAzIDMiIC8+CiAgPHBhdGggZD0iTTEzIDE4SDdhMiAyIDAgMCAxLTItMlY2IiAvPgogIDxwYXRoIGQ9Im0yMiAxNS0zIDMtMy0zIiAvPgogIDxwYXRoIGQ9Ik0xMSA2aDZhMiAyIDAgMCAxIDIgMnYxMCIgLz4KPC9zdmc+Cg==) - https://lucide.dev/icons/repeat-2
		* @see https://lucide.dev/guide/packages/lucide-svelte - Documentation
		*
		* @param {Object} props - Lucide icons props and any valid SVG attribute
		* @returns {FunctionalComponent} Svelte component
		*
		*/
		Icon($$anchor, spread_props({ name: "repeat-2" }, () => $$sanitized_props, {
			get iconNode() {
				return iconNode;
			},
			children: ($$anchor, $$slotProps) => {
				var fragment_1 = comment();
				slot(first_child(fragment_1), $$props, "default", {}, null);
				append($$anchor, fragment_1);
			},
			$$slots: { default: true }
		}));
	}
	//#endregion
	//#region node_modules/lucide-svelte/dist/icons/send.svelte
	function Send($$anchor, $$props) {
		const $$sanitized_props = legacy_rest_props($$props, [
			"children",
			"$$slots",
			"$$events",
			"$$legacy"
		]);
		/**
		* @license lucide-svelte v1.0.1 - ISC
		*
		* ISC License
		*
		* Copyright (c) 2026 Lucide Icons and Contributors
		*
		* Permission to use, copy, modify, and/or distribute this software for any
		* purpose with or without fee is hereby granted, provided that the above
		* copyright notice and this permission notice appear in all copies.
		*
		* THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
		* WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
		* MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
		* ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
		* WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
		* ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
		* OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
		*
		* ---
		*
		* The following Lucide icons are derived from the Feather project:
		*
		* airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
		*
		* The MIT License (MIT) (for the icons listed above)
		*
		* Copyright (c) 2013-present Cole Bemis
		*
		* Permission is hereby granted, free of charge, to any person obtaining a copy
		* of this software and associated documentation files (the "Software"), to deal
		* in the Software without restriction, including without limitation the rights
		* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
		* copies of the Software, and to permit persons to whom the Software is
		* furnished to do so, subject to the following conditions:
		*
		* The above copyright notice and this permission notice shall be included in all
		* copies or substantial portions of the Software.
		*
		* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
		* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
		* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
		* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
		* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
		* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
		* SOFTWARE.
		*
		*/
		const iconNode = [["path", { "d": "M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z" }], ["path", { "d": "m21.854 2.147-10.94 10.939" }]];
		/**
		* @component @name Send
		* @description Lucide SVG icon component, renders SVG Element with children.
		*
		* @preview ![img](data:image/svg+xml;base64,PHN2ZyAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogIHdpZHRoPSIyNCIKICBoZWlnaHQ9IjI0IgogIHZpZXdCb3g9IjAgMCAyNCAyNCIKICBmaWxsPSJub25lIgogIHN0cm9rZT0iIzAwMCIgc3R5bGU9ImJhY2tncm91bmQtY29sb3I6ICNmZmY7IGJvcmRlci1yYWRpdXM6IDJweCIKICBzdHJva2Utd2lkdGg9IjIiCiAgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIgogIHN0cm9rZS1saW5lam9pbj0icm91bmQiCj4KICA8cGF0aCBkPSJNMTQuNTM2IDIxLjY4NmEuNS41IDAgMCAwIC45MzctLjAyNGw2LjUtMTlhLjQ5Ni40OTYgMCAwIDAtLjYzNS0uNjM1bC0xOSA2LjVhLjUuNSAwIDAgMC0uMDI0LjkzN2w3LjkzIDMuMThhMiAyIDAgMCAxIDEuMTEyIDEuMTF6IiAvPgogIDxwYXRoIGQ9Im0yMS44NTQgMi4xNDctMTAuOTQgMTAuOTM5IiAvPgo8L3N2Zz4K) - https://lucide.dev/icons/send
		* @see https://lucide.dev/guide/packages/lucide-svelte - Documentation
		*
		* @param {Object} props - Lucide icons props and any valid SVG attribute
		* @returns {FunctionalComponent} Svelte component
		*
		*/
		Icon($$anchor, spread_props({ name: "send" }, () => $$sanitized_props, {
			get iconNode() {
				return iconNode;
			},
			children: ($$anchor, $$slotProps) => {
				var fragment_1 = comment();
				slot(first_child(fragment_1), $$props, "default", {}, null);
				append($$anchor, fragment_1);
			},
			$$slots: { default: true }
		}));
	}
	//#endregion
	//#region node_modules/lucide-svelte/dist/icons/settings.svelte
	function Settings($$anchor, $$props) {
		const $$sanitized_props = legacy_rest_props($$props, [
			"children",
			"$$slots",
			"$$events",
			"$$legacy"
		]);
		/**
		* @license lucide-svelte v1.0.1 - ISC
		*
		* ISC License
		*
		* Copyright (c) 2026 Lucide Icons and Contributors
		*
		* Permission to use, copy, modify, and/or distribute this software for any
		* purpose with or without fee is hereby granted, provided that the above
		* copyright notice and this permission notice appear in all copies.
		*
		* THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
		* WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
		* MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
		* ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
		* WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
		* ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
		* OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
		*
		* ---
		*
		* The following Lucide icons are derived from the Feather project:
		*
		* airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
		*
		* The MIT License (MIT) (for the icons listed above)
		*
		* Copyright (c) 2013-present Cole Bemis
		*
		* Permission is hereby granted, free of charge, to any person obtaining a copy
		* of this software and associated documentation files (the "Software"), to deal
		* in the Software without restriction, including without limitation the rights
		* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
		* copies of the Software, and to permit persons to whom the Software is
		* furnished to do so, subject to the following conditions:
		*
		* The above copyright notice and this permission notice shall be included in all
		* copies or substantial portions of the Software.
		*
		* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
		* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
		* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
		* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
		* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
		* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
		* SOFTWARE.
		*
		*/
		const iconNode = [["path", { "d": "M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915" }], ["circle", {
			"cx": "12",
			"cy": "12",
			"r": "3"
		}]];
		/**
		* @component @name Settings
		* @description Lucide SVG icon component, renders SVG Element with children.
		*
		* @preview ![img](data:image/svg+xml;base64,PHN2ZyAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogIHdpZHRoPSIyNCIKICBoZWlnaHQ9IjI0IgogIHZpZXdCb3g9IjAgMCAyNCAyNCIKICBmaWxsPSJub25lIgogIHN0cm9rZT0iIzAwMCIgc3R5bGU9ImJhY2tncm91bmQtY29sb3I6ICNmZmY7IGJvcmRlci1yYWRpdXM6IDJweCIKICBzdHJva2Utd2lkdGg9IjIiCiAgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIgogIHN0cm9rZS1saW5lam9pbj0icm91bmQiCj4KICA8cGF0aCBkPSJNOS42NzEgNC4xMzZhMi4zNCAyLjM0IDAgMCAxIDQuNjU5IDAgMi4zNCAyLjM0IDAgMCAwIDMuMzE5IDEuOTE1IDIuMzQgMi4zNCAwIDAgMSAyLjMzIDQuMDMzIDIuMzQgMi4zNCAwIDAgMCAwIDMuODMxIDIuMzQgMi4zNCAwIDAgMS0yLjMzIDQuMDMzIDIuMzQgMi4zNCAwIDAgMC0zLjMxOSAxLjkxNSAyLjM0IDIuMzQgMCAwIDEtNC42NTkgMCAyLjM0IDIuMzQgMCAwIDAtMy4zMi0xLjkxNSAyLjM0IDIuMzQgMCAwIDEtMi4zMy00LjAzMyAyLjM0IDIuMzQgMCAwIDAgMC0zLjgzMUEyLjM0IDIuMzQgMCAwIDEgNi4zNSA2LjA1MWEyLjM0IDIuMzQgMCAwIDAgMy4zMTktMS45MTUiIC8+CiAgPGNpcmNsZSBjeD0iMTIiIGN5PSIxMiIgcj0iMyIgLz4KPC9zdmc+Cg==) - https://lucide.dev/icons/settings
		* @see https://lucide.dev/guide/packages/lucide-svelte - Documentation
		*
		* @param {Object} props - Lucide icons props and any valid SVG attribute
		* @returns {FunctionalComponent} Svelte component
		*
		*/
		Icon($$anchor, spread_props({ name: "settings" }, () => $$sanitized_props, {
			get iconNode() {
				return iconNode;
			},
			children: ($$anchor, $$slotProps) => {
				var fragment_1 = comment();
				slot(first_child(fragment_1), $$props, "default", {}, null);
				append($$anchor, fragment_1);
			},
			$$slots: { default: true }
		}));
	}
	//#endregion
	//#region node_modules/lucide-svelte/dist/icons/ticket.svelte
	function Ticket($$anchor, $$props) {
		const $$sanitized_props = legacy_rest_props($$props, [
			"children",
			"$$slots",
			"$$events",
			"$$legacy"
		]);
		/**
		* @license lucide-svelte v1.0.1 - ISC
		*
		* ISC License
		*
		* Copyright (c) 2026 Lucide Icons and Contributors
		*
		* Permission to use, copy, modify, and/or distribute this software for any
		* purpose with or without fee is hereby granted, provided that the above
		* copyright notice and this permission notice appear in all copies.
		*
		* THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
		* WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
		* MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
		* ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
		* WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
		* ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
		* OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
		*
		* ---
		*
		* The following Lucide icons are derived from the Feather project:
		*
		* airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
		*
		* The MIT License (MIT) (for the icons listed above)
		*
		* Copyright (c) 2013-present Cole Bemis
		*
		* Permission is hereby granted, free of charge, to any person obtaining a copy
		* of this software and associated documentation files (the "Software"), to deal
		* in the Software without restriction, including without limitation the rights
		* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
		* copies of the Software, and to permit persons to whom the Software is
		* furnished to do so, subject to the following conditions:
		*
		* The above copyright notice and this permission notice shall be included in all
		* copies or substantial portions of the Software.
		*
		* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
		* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
		* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
		* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
		* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
		* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
		* SOFTWARE.
		*
		*/
		const iconNode = [
			["path", { "d": "M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z" }],
			["path", { "d": "M13 5v2" }],
			["path", { "d": "M13 17v2" }],
			["path", { "d": "M13 11v2" }]
		];
		/**
		* @component @name Ticket
		* @description Lucide SVG icon component, renders SVG Element with children.
		*
		* @preview ![img](data:image/svg+xml;base64,PHN2ZyAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogIHdpZHRoPSIyNCIKICBoZWlnaHQ9IjI0IgogIHZpZXdCb3g9IjAgMCAyNCAyNCIKICBmaWxsPSJub25lIgogIHN0cm9rZT0iIzAwMCIgc3R5bGU9ImJhY2tncm91bmQtY29sb3I6ICNmZmY7IGJvcmRlci1yYWRpdXM6IDJweCIKICBzdHJva2Utd2lkdGg9IjIiCiAgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIgogIHN0cm9rZS1saW5lam9pbj0icm91bmQiCj4KICA8cGF0aCBkPSJNMiA5YTMgMyAwIDAgMSAwIDZ2MmEyIDIgMCAwIDAgMiAyaDE2YTIgMiAwIDAgMCAyLTJ2LTJhMyAzIDAgMCAxIDAtNlY3YTIgMiAwIDAgMC0yLTJINGEyIDIgMCAwIDAtMiAyWiIgLz4KICA8cGF0aCBkPSJNMTMgNXYyIiAvPgogIDxwYXRoIGQ9Ik0xMyAxN3YyIiAvPgogIDxwYXRoIGQ9Ik0xMyAxMXYyIiAvPgo8L3N2Zz4K) - https://lucide.dev/icons/ticket
		* @see https://lucide.dev/guide/packages/lucide-svelte - Documentation
		*
		* @param {Object} props - Lucide icons props and any valid SVG attribute
		* @returns {FunctionalComponent} Svelte component
		*
		*/
		Icon($$anchor, spread_props({ name: "ticket" }, () => $$sanitized_props, {
			get iconNode() {
				return iconNode;
			},
			children: ($$anchor, $$slotProps) => {
				var fragment_1 = comment();
				slot(first_child(fragment_1), $$props, "default", {}, null);
				append($$anchor, fragment_1);
			},
			$$slots: { default: true }
		}));
	}
	//#endregion
	//#region node_modules/lucide-svelte/dist/icons/user-round.svelte
	function User_round($$anchor, $$props) {
		const $$sanitized_props = legacy_rest_props($$props, [
			"children",
			"$$slots",
			"$$events",
			"$$legacy"
		]);
		/**
		* @license lucide-svelte v1.0.1 - ISC
		*
		* ISC License
		*
		* Copyright (c) 2026 Lucide Icons and Contributors
		*
		* Permission to use, copy, modify, and/or distribute this software for any
		* purpose with or without fee is hereby granted, provided that the above
		* copyright notice and this permission notice appear in all copies.
		*
		* THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
		* WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
		* MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
		* ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
		* WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
		* ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
		* OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
		*
		* ---
		*
		* The following Lucide icons are derived from the Feather project:
		*
		* airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
		*
		* The MIT License (MIT) (for the icons listed above)
		*
		* Copyright (c) 2013-present Cole Bemis
		*
		* Permission is hereby granted, free of charge, to any person obtaining a copy
		* of this software and associated documentation files (the "Software"), to deal
		* in the Software without restriction, including without limitation the rights
		* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
		* copies of the Software, and to permit persons to whom the Software is
		* furnished to do so, subject to the following conditions:
		*
		* The above copyright notice and this permission notice shall be included in all
		* copies or substantial portions of the Software.
		*
		* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
		* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
		* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
		* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
		* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
		* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
		* SOFTWARE.
		*
		*/
		const iconNode = [["circle", {
			"cx": "12",
			"cy": "8",
			"r": "5"
		}], ["path", { "d": "M20 21a8 8 0 0 0-16 0" }]];
		/**
		* @component @name UserRound
		* @description Lucide SVG icon component, renders SVG Element with children.
		*
		* @preview ![img](data:image/svg+xml;base64,PHN2ZyAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogIHdpZHRoPSIyNCIKICBoZWlnaHQ9IjI0IgogIHZpZXdCb3g9IjAgMCAyNCAyNCIKICBmaWxsPSJub25lIgogIHN0cm9rZT0iIzAwMCIgc3R5bGU9ImJhY2tncm91bmQtY29sb3I6ICNmZmY7IGJvcmRlci1yYWRpdXM6IDJweCIKICBzdHJva2Utd2lkdGg9IjIiCiAgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIgogIHN0cm9rZS1saW5lam9pbj0icm91bmQiCj4KICA8Y2lyY2xlIGN4PSIxMiIgY3k9IjgiIHI9IjUiIC8+CiAgPHBhdGggZD0iTTIwIDIxYTggOCAwIDAgMC0xNiAwIiAvPgo8L3N2Zz4K) - https://lucide.dev/icons/user-round
		* @see https://lucide.dev/guide/packages/lucide-svelte - Documentation
		*
		* @param {Object} props - Lucide icons props and any valid SVG attribute
		* @returns {FunctionalComponent} Svelte component
		*
		*/
		Icon($$anchor, spread_props({ name: "user-round" }, () => $$sanitized_props, {
			get iconNode() {
				return iconNode;
			},
			children: ($$anchor, $$slotProps) => {
				var fragment_1 = comment();
				slot(first_child(fragment_1), $$props, "default", {}, null);
				append($$anchor, fragment_1);
			},
			$$slots: { default: true }
		}));
	}
	//#endregion
	//#region node_modules/lucide-svelte/dist/icons/wallet-cards.svelte
	function Wallet_cards($$anchor, $$props) {
		const $$sanitized_props = legacy_rest_props($$props, [
			"children",
			"$$slots",
			"$$events",
			"$$legacy"
		]);
		/**
		* @license lucide-svelte v1.0.1 - ISC
		*
		* ISC License
		*
		* Copyright (c) 2026 Lucide Icons and Contributors
		*
		* Permission to use, copy, modify, and/or distribute this software for any
		* purpose with or without fee is hereby granted, provided that the above
		* copyright notice and this permission notice appear in all copies.
		*
		* THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
		* WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
		* MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
		* ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
		* WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
		* ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
		* OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
		*
		* ---
		*
		* The following Lucide icons are derived from the Feather project:
		*
		* airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
		*
		* The MIT License (MIT) (for the icons listed above)
		*
		* Copyright (c) 2013-present Cole Bemis
		*
		* Permission is hereby granted, free of charge, to any person obtaining a copy
		* of this software and associated documentation files (the "Software"), to deal
		* in the Software without restriction, including without limitation the rights
		* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
		* copies of the Software, and to permit persons to whom the Software is
		* furnished to do so, subject to the following conditions:
		*
		* The above copyright notice and this permission notice shall be included in all
		* copies or substantial portions of the Software.
		*
		* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
		* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
		* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
		* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
		* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
		* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
		* SOFTWARE.
		*
		*/
		const iconNode = [
			["rect", {
				"width": "18",
				"height": "18",
				"x": "3",
				"y": "3",
				"rx": "2"
			}],
			["path", { "d": "M3 9a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2" }],
			["path", { "d": "M3 11h3c.8 0 1.6.3 2.1.9l1.1.9c1.6 1.6 4.1 1.6 5.7 0l1.1-.9c.5-.5 1.3-.9 2.1-.9H21" }]
		];
		/**
		* @component @name WalletCards
		* @description Lucide SVG icon component, renders SVG Element with children.
		*
		* @preview ![img](data:image/svg+xml;base64,PHN2ZyAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogIHdpZHRoPSIyNCIKICBoZWlnaHQ9IjI0IgogIHZpZXdCb3g9IjAgMCAyNCAyNCIKICBmaWxsPSJub25lIgogIHN0cm9rZT0iIzAwMCIgc3R5bGU9ImJhY2tncm91bmQtY29sb3I6ICNmZmY7IGJvcmRlci1yYWRpdXM6IDJweCIKICBzdHJva2Utd2lkdGg9IjIiCiAgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIgogIHN0cm9rZS1saW5lam9pbj0icm91bmQiCj4KICA8cmVjdCB3aWR0aD0iMTgiIGhlaWdodD0iMTgiIHg9IjMiIHk9IjMiIHJ4PSIyIiAvPgogIDxwYXRoIGQ9Ik0zIDlhMiAyIDAgMCAxIDItMmgxNGEyIDIgMCAwIDEgMiAyIiAvPgogIDxwYXRoIGQ9Ik0zIDExaDNjLjggMCAxLjYuMyAyLjEuOWwxLjEuOWMxLjYgMS42IDQuMSAxLjYgNS43IDBsMS4xLS45Yy41LS41IDEuMy0uOSAyLjEtLjlIMjEiIC8+Cjwvc3ZnPgo=) - https://lucide.dev/icons/wallet-cards
		* @see https://lucide.dev/guide/packages/lucide-svelte - Documentation
		*
		* @param {Object} props - Lucide icons props and any valid SVG attribute
		* @returns {FunctionalComponent} Svelte component
		*
		*/
		Icon($$anchor, spread_props({ name: "wallet-cards" }, () => $$sanitized_props, {
			get iconNode() {
				return iconNode;
			},
			children: ($$anchor, $$slotProps) => {
				var fragment_1 = comment();
				slot(first_child(fragment_1), $$props, "default", {}, null);
				append($$anchor, fragment_1);
			},
			$$slots: { default: true }
		}));
	}
	//#endregion
	//#region node_modules/lucide-svelte/dist/icons/x.svelte
	function X($$anchor, $$props) {
		const $$sanitized_props = legacy_rest_props($$props, [
			"children",
			"$$slots",
			"$$events",
			"$$legacy"
		]);
		/**
		* @license lucide-svelte v1.0.1 - ISC
		*
		* ISC License
		*
		* Copyright (c) 2026 Lucide Icons and Contributors
		*
		* Permission to use, copy, modify, and/or distribute this software for any
		* purpose with or without fee is hereby granted, provided that the above
		* copyright notice and this permission notice appear in all copies.
		*
		* THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
		* WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
		* MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
		* ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
		* WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
		* ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
		* OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
		*
		* ---
		*
		* The following Lucide icons are derived from the Feather project:
		*
		* airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
		*
		* The MIT License (MIT) (for the icons listed above)
		*
		* Copyright (c) 2013-present Cole Bemis
		*
		* Permission is hereby granted, free of charge, to any person obtaining a copy
		* of this software and associated documentation files (the "Software"), to deal
		* in the Software without restriction, including without limitation the rights
		* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
		* copies of the Software, and to permit persons to whom the Software is
		* furnished to do so, subject to the following conditions:
		*
		* The above copyright notice and this permission notice shall be included in all
		* copies or substantial portions of the Software.
		*
		* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
		* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
		* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
		* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
		* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
		* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
		* SOFTWARE.
		*
		*/
		const iconNode = [["path", { "d": "M18 6 6 18" }], ["path", { "d": "m6 6 12 12" }]];
		/**
		* @component @name X
		* @description Lucide SVG icon component, renders SVG Element with children.
		*
		* @preview ![img](data:image/svg+xml;base64,PHN2ZyAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogIHdpZHRoPSIyNCIKICBoZWlnaHQ9IjI0IgogIHZpZXdCb3g9IjAgMCAyNCAyNCIKICBmaWxsPSJub25lIgogIHN0cm9rZT0iIzAwMCIgc3R5bGU9ImJhY2tncm91bmQtY29sb3I6ICNmZmY7IGJvcmRlci1yYWRpdXM6IDJweCIKICBzdHJva2Utd2lkdGg9IjIiCiAgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIgogIHN0cm9rZS1saW5lam9pbj0icm91bmQiCj4KICA8cGF0aCBkPSJNMTggNiA2IDE4IiAvPgogIDxwYXRoIGQ9Im02IDYgMTIgMTIiIC8+Cjwvc3ZnPgo=) - https://lucide.dev/icons/x
		* @see https://lucide.dev/guide/packages/lucide-svelte - Documentation
		*
		* @param {Object} props - Lucide icons props and any valid SVG attribute
		* @returns {FunctionalComponent} Svelte component
		*
		*/
		Icon($$anchor, spread_props({ name: "x" }, () => $$sanitized_props, {
			get iconNode() {
				return iconNode;
			},
			children: ($$anchor, $$slotProps) => {
				var fragment_1 = comment();
				slot(first_child(fragment_1), $$props, "default", {}, null);
				append($$anchor, fragment_1);
			},
			$$slots: { default: true }
		}));
	}
	//#endregion
	//#region node_modules/lucide-svelte/dist/icons/zap.svelte
	function Zap($$anchor, $$props) {
		const $$sanitized_props = legacy_rest_props($$props, [
			"children",
			"$$slots",
			"$$events",
			"$$legacy"
		]);
		/**
		* @license lucide-svelte v1.0.1 - ISC
		*
		* ISC License
		*
		* Copyright (c) 2026 Lucide Icons and Contributors
		*
		* Permission to use, copy, modify, and/or distribute this software for any
		* purpose with or without fee is hereby granted, provided that the above
		* copyright notice and this permission notice appear in all copies.
		*
		* THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
		* WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
		* MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
		* ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
		* WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
		* ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
		* OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
		*
		* ---
		*
		* The following Lucide icons are derived from the Feather project:
		*
		* airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out
		*
		* The MIT License (MIT) (for the icons listed above)
		*
		* Copyright (c) 2013-present Cole Bemis
		*
		* Permission is hereby granted, free of charge, to any person obtaining a copy
		* of this software and associated documentation files (the "Software"), to deal
		* in the Software without restriction, including without limitation the rights
		* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
		* copies of the Software, and to permit persons to whom the Software is
		* furnished to do so, subject to the following conditions:
		*
		* The above copyright notice and this permission notice shall be included in all
		* copies or substantial portions of the Software.
		*
		* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
		* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
		* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
		* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
		* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
		* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
		* SOFTWARE.
		*
		*/
		const iconNode = [["path", { "d": "M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z" }]];
		/**
		* @component @name Zap
		* @description Lucide SVG icon component, renders SVG Element with children.
		*
		* @preview ![img](data:image/svg+xml;base64,PHN2ZyAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogIHdpZHRoPSIyNCIKICBoZWlnaHQ9IjI0IgogIHZpZXdCb3g9IjAgMCAyNCAyNCIKICBmaWxsPSJub25lIgogIHN0cm9rZT0iIzAwMCIgc3R5bGU9ImJhY2tncm91bmQtY29sb3I6ICNmZmY7IGJvcmRlci1yYWRpdXM6IDJweCIKICBzdHJva2Utd2lkdGg9IjIiCiAgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIgogIHN0cm9rZS1saW5lam9pbj0icm91bmQiCj4KICA8cGF0aCBkPSJNNCAxNGExIDEgMCAwIDEtLjc4LTEuNjNsOS45LTEwLjJhLjUuNSAwIDAgMSAuODYuNDZsLTEuOTIgNi4wMkExIDEgMCAwIDAgMTMgMTBoN2ExIDEgMCAwIDEgLjc4IDEuNjNsLTkuOSAxMC4yYS41LjUgMCAwIDEtLjg2LS40NmwxLjkyLTYuMDJBMSAxIDAgMCAwIDExIDE0eiIgLz4KPC9zdmc+Cg==) - https://lucide.dev/icons/zap
		* @see https://lucide.dev/guide/packages/lucide-svelte - Documentation
		*
		* @param {Object} props - Lucide icons props and any valid SVG attribute
		* @returns {FunctionalComponent} Svelte component
		*
		*/
		Icon($$anchor, spread_props({ name: "zap" }, () => $$sanitized_props, {
			get iconNode() {
				return iconNode;
			},
			children: ($$anchor, $$slotProps) => {
				var fragment_1 = comment();
				slot(first_child(fragment_1), $$props, "default", {}, null);
				append($$anchor, fragment_1);
			},
			$$slots: { default: true }
		}));
	}
	//#endregion
	//#region node_modules/tailwind-merge/dist/bundle-mjs.mjs
	/**
	* Concatenates two arrays faster than the array spread operator.
	*/
	var concatArrays = (array1, array2) => {
		const combinedArray = new Array(array1.length + array2.length);
		for (let i = 0; i < array1.length; i++) combinedArray[i] = array1[i];
		for (let i = 0; i < array2.length; i++) combinedArray[array1.length + i] = array2[i];
		return combinedArray;
	};
	var createClassValidatorObject = (classGroupId, validator) => ({
		classGroupId,
		validator
	});
	var createClassPartObject = (nextPart = /* @__PURE__ */ new Map(), validators = null, classGroupId) => ({
		nextPart,
		validators,
		classGroupId
	});
	var CLASS_PART_SEPARATOR = "-";
	var EMPTY_CONFLICTS = [];
	var ARBITRARY_PROPERTY_PREFIX = "arbitrary..";
	var createClassGroupUtils = (config) => {
		const classMap = createClassMap(config);
		const { conflictingClassGroups, conflictingClassGroupModifiers } = config;
		const getClassGroupId = (className) => {
			if (className.startsWith("[") && className.endsWith("]")) return getGroupIdForArbitraryProperty(className);
			const classParts = className.split(CLASS_PART_SEPARATOR);
			return getGroupRecursive(classParts, classParts[0] === "" && classParts.length > 1 ? 1 : 0, classMap);
		};
		const getConflictingClassGroupIds = (classGroupId, hasPostfixModifier) => {
			if (hasPostfixModifier) {
				const modifierConflicts = conflictingClassGroupModifiers[classGroupId];
				const baseConflicts = conflictingClassGroups[classGroupId];
				if (modifierConflicts) {
					if (baseConflicts) return concatArrays(baseConflicts, modifierConflicts);
					return modifierConflicts;
				}
				return baseConflicts || EMPTY_CONFLICTS;
			}
			return conflictingClassGroups[classGroupId] || EMPTY_CONFLICTS;
		};
		return {
			getClassGroupId,
			getConflictingClassGroupIds
		};
	};
	var getGroupRecursive = (classParts, startIndex, classPartObject) => {
		if (classParts.length - startIndex === 0) return classPartObject.classGroupId;
		const currentClassPart = classParts[startIndex];
		const nextClassPartObject = classPartObject.nextPart.get(currentClassPart);
		if (nextClassPartObject) {
			const result = getGroupRecursive(classParts, startIndex + 1, nextClassPartObject);
			if (result) return result;
		}
		const validators = classPartObject.validators;
		if (validators === null) return;
		const classRest = startIndex === 0 ? classParts.join(CLASS_PART_SEPARATOR) : classParts.slice(startIndex).join(CLASS_PART_SEPARATOR);
		const validatorsLength = validators.length;
		for (let i = 0; i < validatorsLength; i++) {
			const validatorObj = validators[i];
			if (validatorObj.validator(classRest)) return validatorObj.classGroupId;
		}
	};
	/**
	* Get the class group ID for an arbitrary property.
	*
	* @param className - The class name to get the group ID for. Is expected to be string starting with `[` and ending with `]`.
	*/
	var getGroupIdForArbitraryProperty = (className) => className.slice(1, -1).indexOf(":") === -1 ? void 0 : (() => {
		const content = className.slice(1, -1);
		const colonIndex = content.indexOf(":");
		const property = content.slice(0, colonIndex);
		return property ? ARBITRARY_PROPERTY_PREFIX + property : void 0;
	})();
	/**
	* Exported for testing only
	*/
	var createClassMap = (config) => {
		const { theme, classGroups } = config;
		return processClassGroups(classGroups, theme);
	};
	var processClassGroups = (classGroups, theme) => {
		const classMap = createClassPartObject();
		for (const classGroupId in classGroups) {
			const group = classGroups[classGroupId];
			processClassesRecursively(group, classMap, classGroupId, theme);
		}
		return classMap;
	};
	var processClassesRecursively = (classGroup, classPartObject, classGroupId, theme) => {
		const len = classGroup.length;
		for (let i = 0; i < len; i++) {
			const classDefinition = classGroup[i];
			processClassDefinition(classDefinition, classPartObject, classGroupId, theme);
		}
	};
	var processClassDefinition = (classDefinition, classPartObject, classGroupId, theme) => {
		if (typeof classDefinition === "string") {
			processStringDefinition(classDefinition, classPartObject, classGroupId);
			return;
		}
		if (typeof classDefinition === "function") {
			processFunctionDefinition(classDefinition, classPartObject, classGroupId, theme);
			return;
		}
		processObjectDefinition(classDefinition, classPartObject, classGroupId, theme);
	};
	var processStringDefinition = (classDefinition, classPartObject, classGroupId) => {
		const classPartObjectToEdit = classDefinition === "" ? classPartObject : getPart(classPartObject, classDefinition);
		classPartObjectToEdit.classGroupId = classGroupId;
	};
	var processFunctionDefinition = (classDefinition, classPartObject, classGroupId, theme) => {
		if (isThemeGetter(classDefinition)) {
			processClassesRecursively(classDefinition(theme), classPartObject, classGroupId, theme);
			return;
		}
		if (classPartObject.validators === null) classPartObject.validators = [];
		classPartObject.validators.push(createClassValidatorObject(classGroupId, classDefinition));
	};
	var processObjectDefinition = (classDefinition, classPartObject, classGroupId, theme) => {
		const entries = Object.entries(classDefinition);
		const len = entries.length;
		for (let i = 0; i < len; i++) {
			const [key, value] = entries[i];
			processClassesRecursively(value, getPart(classPartObject, key), classGroupId, theme);
		}
	};
	var getPart = (classPartObject, path) => {
		let current = classPartObject;
		const parts = path.split(CLASS_PART_SEPARATOR);
		const len = parts.length;
		for (let i = 0; i < len; i++) {
			const part = parts[i];
			let next = current.nextPart.get(part);
			if (!next) {
				next = createClassPartObject();
				current.nextPart.set(part, next);
			}
			current = next;
		}
		return current;
	};
	var isThemeGetter = (func) => "isThemeGetter" in func && func.isThemeGetter === true;
	var createLruCache = (maxCacheSize) => {
		if (maxCacheSize < 1) return {
			get: () => void 0,
			set: () => {}
		};
		let cacheSize = 0;
		let cache = Object.create(null);
		let previousCache = Object.create(null);
		const update = (key, value) => {
			cache[key] = value;
			cacheSize++;
			if (cacheSize > maxCacheSize) {
				cacheSize = 0;
				previousCache = cache;
				cache = Object.create(null);
			}
		};
		return {
			get(key) {
				let value = cache[key];
				if (value !== void 0) return value;
				if ((value = previousCache[key]) !== void 0) {
					update(key, value);
					return value;
				}
			},
			set(key, value) {
				if (key in cache) cache[key] = value;
				else update(key, value);
			}
		};
	};
	var IMPORTANT_MODIFIER = "!";
	var MODIFIER_SEPARATOR = ":";
	var EMPTY_MODIFIERS = [];
	var createResultObject = (modifiers, hasImportantModifier, baseClassName, maybePostfixModifierPosition, isExternal) => ({
		modifiers,
		hasImportantModifier,
		baseClassName,
		maybePostfixModifierPosition,
		isExternal
	});
	var createParseClassName = (config) => {
		const { prefix, experimentalParseClassName } = config;
		/**
		* Parse class name into parts.
		*
		* Inspired by `splitAtTopLevelOnly` used in Tailwind CSS
		* @see https://github.com/tailwindlabs/tailwindcss/blob/v3.2.2/src/util/splitAtTopLevelOnly.js
		*/
		let parseClassName = (className) => {
			const modifiers = [];
			let bracketDepth = 0;
			let parenDepth = 0;
			let modifierStart = 0;
			let postfixModifierPosition;
			const len = className.length;
			for (let index = 0; index < len; index++) {
				const currentCharacter = className[index];
				if (bracketDepth === 0 && parenDepth === 0) {
					if (currentCharacter === MODIFIER_SEPARATOR) {
						modifiers.push(className.slice(modifierStart, index));
						modifierStart = index + 1;
						continue;
					}
					if (currentCharacter === "/") {
						postfixModifierPosition = index;
						continue;
					}
				}
				if (currentCharacter === "[") bracketDepth++;
				else if (currentCharacter === "]") bracketDepth--;
				else if (currentCharacter === "(") parenDepth++;
				else if (currentCharacter === ")") parenDepth--;
			}
			const baseClassNameWithImportantModifier = modifiers.length === 0 ? className : className.slice(modifierStart);
			let baseClassName = baseClassNameWithImportantModifier;
			let hasImportantModifier = false;
			if (baseClassNameWithImportantModifier.endsWith(IMPORTANT_MODIFIER)) {
				baseClassName = baseClassNameWithImportantModifier.slice(0, -1);
				hasImportantModifier = true;
			} else if (baseClassNameWithImportantModifier.startsWith(IMPORTANT_MODIFIER)) {
				baseClassName = baseClassNameWithImportantModifier.slice(1);
				hasImportantModifier = true;
			}
			const maybePostfixModifierPosition = postfixModifierPosition && postfixModifierPosition > modifierStart ? postfixModifierPosition - modifierStart : void 0;
			return createResultObject(modifiers, hasImportantModifier, baseClassName, maybePostfixModifierPosition);
		};
		if (prefix) {
			const fullPrefix = prefix + MODIFIER_SEPARATOR;
			const parseClassNameOriginal = parseClassName;
			parseClassName = (className) => className.startsWith(fullPrefix) ? parseClassNameOriginal(className.slice(fullPrefix.length)) : createResultObject(EMPTY_MODIFIERS, false, className, void 0, true);
		}
		if (experimentalParseClassName) {
			const parseClassNameOriginal = parseClassName;
			parseClassName = (className) => experimentalParseClassName({
				className,
				parseClassName: parseClassNameOriginal
			});
		}
		return parseClassName;
	};
	/**
	* Sorts modifiers according to following schema:
	* - Predefined modifiers are sorted alphabetically
	* - When an arbitrary variant appears, it must be preserved which modifiers are before and after it
	*/
	var createSortModifiers = (config) => {
		const modifierWeights = /* @__PURE__ */ new Map();
		config.orderSensitiveModifiers.forEach((mod, index) => {
			modifierWeights.set(mod, 1e6 + index);
		});
		return (modifiers) => {
			const result = [];
			let currentSegment = [];
			for (let i = 0; i < modifiers.length; i++) {
				const modifier = modifiers[i];
				const isArbitrary = modifier[0] === "[";
				const isOrderSensitive = modifierWeights.has(modifier);
				if (isArbitrary || isOrderSensitive) {
					if (currentSegment.length > 0) {
						currentSegment.sort();
						result.push(...currentSegment);
						currentSegment = [];
					}
					result.push(modifier);
				} else currentSegment.push(modifier);
			}
			if (currentSegment.length > 0) {
				currentSegment.sort();
				result.push(...currentSegment);
			}
			return result;
		};
	};
	var createConfigUtils = (config) => ({
		cache: createLruCache(config.cacheSize),
		parseClassName: createParseClassName(config),
		sortModifiers: createSortModifiers(config),
		...createClassGroupUtils(config)
	});
	var SPLIT_CLASSES_REGEX = /\s+/;
	var mergeClassList = (classList, configUtils) => {
		const { parseClassName, getClassGroupId, getConflictingClassGroupIds, sortModifiers } = configUtils;
		/**
		* Set of classGroupIds in following format:
		* `{importantModifier}{variantModifiers}{classGroupId}`
		* @example 'float'
		* @example 'hover:focus:bg-color'
		* @example 'md:!pr'
		*/
		const classGroupsInConflict = [];
		const classNames = classList.trim().split(SPLIT_CLASSES_REGEX);
		let result = "";
		for (let index = classNames.length - 1; index >= 0; index -= 1) {
			const originalClassName = classNames[index];
			const { isExternal, modifiers, hasImportantModifier, baseClassName, maybePostfixModifierPosition } = parseClassName(originalClassName);
			if (isExternal) {
				result = originalClassName + (result.length > 0 ? " " + result : result);
				continue;
			}
			let hasPostfixModifier = !!maybePostfixModifierPosition;
			let classGroupId = getClassGroupId(hasPostfixModifier ? baseClassName.substring(0, maybePostfixModifierPosition) : baseClassName);
			if (!classGroupId) {
				if (!hasPostfixModifier) {
					result = originalClassName + (result.length > 0 ? " " + result : result);
					continue;
				}
				classGroupId = getClassGroupId(baseClassName);
				if (!classGroupId) {
					result = originalClassName + (result.length > 0 ? " " + result : result);
					continue;
				}
				hasPostfixModifier = false;
			}
			const variantModifier = modifiers.length === 0 ? "" : modifiers.length === 1 ? modifiers[0] : sortModifiers(modifiers).join(":");
			const modifierId = hasImportantModifier ? variantModifier + IMPORTANT_MODIFIER : variantModifier;
			const classId = modifierId + classGroupId;
			if (classGroupsInConflict.indexOf(classId) > -1) continue;
			classGroupsInConflict.push(classId);
			const conflictGroups = getConflictingClassGroupIds(classGroupId, hasPostfixModifier);
			for (let i = 0; i < conflictGroups.length; ++i) {
				const group = conflictGroups[i];
				classGroupsInConflict.push(modifierId + group);
			}
			result = originalClassName + (result.length > 0 ? " " + result : result);
		}
		return result;
	};
	/**
	* The code in this file is copied from https://github.com/lukeed/clsx and modified to suit the needs of tailwind-merge better.
	*
	* Specifically:
	* - Runtime code from https://github.com/lukeed/clsx/blob/v1.2.1/src/index.js
	* - TypeScript types from https://github.com/lukeed/clsx/blob/v1.2.1/clsx.d.ts
	*
	* Original code has MIT license: Copyright (c) Luke Edwards <luke.edwards05@gmail.com> (lukeed.com)
	*/
	var twJoin = (...classLists) => {
		let index = 0;
		let argument;
		let resolvedValue;
		let string = "";
		while (index < classLists.length) if (argument = classLists[index++]) {
			if (resolvedValue = toValue(argument)) {
				string && (string += " ");
				string += resolvedValue;
			}
		}
		return string;
	};
	var toValue = (mix) => {
		if (typeof mix === "string") return mix;
		let resolvedValue;
		let string = "";
		for (let k = 0; k < mix.length; k++) if (mix[k]) {
			if (resolvedValue = toValue(mix[k])) {
				string && (string += " ");
				string += resolvedValue;
			}
		}
		return string;
	};
	var createTailwindMerge = (createConfigFirst, ...createConfigRest) => {
		let configUtils;
		let cacheGet;
		let cacheSet;
		let functionToCall;
		const initTailwindMerge = (classList) => {
			configUtils = createConfigUtils(createConfigRest.reduce((previousConfig, createConfigCurrent) => createConfigCurrent(previousConfig), createConfigFirst()));
			cacheGet = configUtils.cache.get;
			cacheSet = configUtils.cache.set;
			functionToCall = tailwindMerge;
			return tailwindMerge(classList);
		};
		const tailwindMerge = (classList) => {
			const cachedResult = cacheGet(classList);
			if (cachedResult) return cachedResult;
			const result = mergeClassList(classList, configUtils);
			cacheSet(classList, result);
			return result;
		};
		functionToCall = initTailwindMerge;
		return (...args) => functionToCall(twJoin(...args));
	};
	var fallbackThemeArr = [];
	var fromTheme = (key) => {
		const themeGetter = (theme) => theme[key] || fallbackThemeArr;
		themeGetter.isThemeGetter = true;
		return themeGetter;
	};
	var arbitraryValueRegex = /^\[(?:(\w[\w-]*):)?(.+)\]$/i;
	var arbitraryVariableRegex = /^\((?:(\w[\w-]*):)?(.+)\)$/i;
	var fractionRegex = /^\d+(?:\.\d+)?\/\d+(?:\.\d+)?$/;
	var tshirtUnitRegex = /^(\d+(\.\d+)?)?(xs|sm|md|lg|xl)$/;
	var lengthUnitRegex = /\d+(%|px|r?em|[sdl]?v([hwib]|min|max)|pt|pc|in|cm|mm|cap|ch|ex|r?lh|cq(w|h|i|b|min|max))|\b(calc|min|max|clamp)\(.+\)|^0$/;
	var colorFunctionRegex = /^(rgba?|hsla?|hwb|(ok)?(lab|lch)|color-mix)\(.+\)$/;
	var shadowRegex = /^(inset_)?-?((\d+)?\.?(\d+)[a-z]+|0)_-?((\d+)?\.?(\d+)[a-z]+|0)/;
	var imageRegex = /^(url|image|image-set|cross-fade|element|(repeating-)?(linear|radial|conic)-gradient)\(.+\)$/;
	var isFraction = (value) => fractionRegex.test(value);
	var isNumber = (value) => !!value && !Number.isNaN(Number(value));
	var isInteger = (value) => !!value && Number.isInteger(Number(value));
	var isPercent = (value) => value.endsWith("%") && isNumber(value.slice(0, -1));
	var isTshirtSize = (value) => tshirtUnitRegex.test(value);
	var isAny = () => true;
	var isLengthOnly = (value) => lengthUnitRegex.test(value) && !colorFunctionRegex.test(value);
	var isNever = () => false;
	var isShadow = (value) => shadowRegex.test(value);
	var isImage = (value) => imageRegex.test(value);
	var isAnyNonArbitrary = (value) => !isArbitraryValue(value) && !isArbitraryVariable(value);
	var isArbitrarySize = (value) => getIsArbitraryValue(value, isLabelSize, isNever);
	var isArbitraryValue = (value) => arbitraryValueRegex.test(value);
	var isArbitraryLength = (value) => getIsArbitraryValue(value, isLabelLength, isLengthOnly);
	var isArbitraryNumber = (value) => getIsArbitraryValue(value, isLabelNumber, isNumber);
	var isArbitraryWeight = (value) => getIsArbitraryValue(value, isLabelWeight, isAny);
	var isArbitraryFamilyName = (value) => getIsArbitraryValue(value, isLabelFamilyName, isNever);
	var isArbitraryPosition = (value) => getIsArbitraryValue(value, isLabelPosition, isNever);
	var isArbitraryImage = (value) => getIsArbitraryValue(value, isLabelImage, isImage);
	var isArbitraryShadow = (value) => getIsArbitraryValue(value, isLabelShadow, isShadow);
	var isArbitraryVariable = (value) => arbitraryVariableRegex.test(value);
	var isArbitraryVariableLength = (value) => getIsArbitraryVariable(value, isLabelLength);
	var isArbitraryVariableFamilyName = (value) => getIsArbitraryVariable(value, isLabelFamilyName);
	var isArbitraryVariablePosition = (value) => getIsArbitraryVariable(value, isLabelPosition);
	var isArbitraryVariableSize = (value) => getIsArbitraryVariable(value, isLabelSize);
	var isArbitraryVariableImage = (value) => getIsArbitraryVariable(value, isLabelImage);
	var isArbitraryVariableShadow = (value) => getIsArbitraryVariable(value, isLabelShadow, true);
	var isArbitraryVariableWeight = (value) => getIsArbitraryVariable(value, isLabelWeight, true);
	var getIsArbitraryValue = (value, testLabel, testValue) => {
		const result = arbitraryValueRegex.exec(value);
		if (result) {
			if (result[1]) return testLabel(result[1]);
			return testValue(result[2]);
		}
		return false;
	};
	var getIsArbitraryVariable = (value, testLabel, shouldMatchNoLabel = false) => {
		const result = arbitraryVariableRegex.exec(value);
		if (result) {
			if (result[1]) return testLabel(result[1]);
			return shouldMatchNoLabel;
		}
		return false;
	};
	var isLabelPosition = (label) => label === "position" || label === "percentage";
	var isLabelImage = (label) => label === "image" || label === "url";
	var isLabelSize = (label) => label === "length" || label === "size" || label === "bg-size";
	var isLabelLength = (label) => label === "length";
	var isLabelNumber = (label) => label === "number";
	var isLabelFamilyName = (label) => label === "family-name";
	var isLabelWeight = (label) => label === "number" || label === "weight";
	var isLabelShadow = (label) => label === "shadow";
	var getDefaultConfig = () => {
		/**
		* Theme getters for theme variable namespaces
		* @see https://tailwindcss.com/docs/theme#theme-variable-namespaces
		*/
		const themeColor = fromTheme("color");
		const themeFont = fromTheme("font");
		const themeText = fromTheme("text");
		const themeFontWeight = fromTheme("font-weight");
		const themeTracking = fromTheme("tracking");
		const themeLeading = fromTheme("leading");
		const themeBreakpoint = fromTheme("breakpoint");
		const themeContainer = fromTheme("container");
		const themeSpacing = fromTheme("spacing");
		const themeRadius = fromTheme("radius");
		const themeShadow = fromTheme("shadow");
		const themeInsetShadow = fromTheme("inset-shadow");
		const themeTextShadow = fromTheme("text-shadow");
		const themeDropShadow = fromTheme("drop-shadow");
		const themeBlur = fromTheme("blur");
		const themePerspective = fromTheme("perspective");
		const themeAspect = fromTheme("aspect");
		const themeEase = fromTheme("ease");
		const themeAnimate = fromTheme("animate");
		/**
		* Helpers to avoid repeating the same scales
		*
		* We use functions that create a new array every time they're called instead of static arrays.
		* This ensures that users who modify any scale by mutating the array (e.g. with `array.push(element)`) don't accidentally mutate arrays in other parts of the config.
		*/
		const scaleBreak = () => [
			"auto",
			"avoid",
			"all",
			"avoid-page",
			"page",
			"left",
			"right",
			"column"
		];
		const scalePosition = () => [
			"center",
			"top",
			"bottom",
			"left",
			"right",
			"top-left",
			"left-top",
			"top-right",
			"right-top",
			"bottom-right",
			"right-bottom",
			"bottom-left",
			"left-bottom"
		];
		const scalePositionWithArbitrary = () => [
			...scalePosition(),
			isArbitraryVariable,
			isArbitraryValue
		];
		const scaleOverflow = () => [
			"auto",
			"hidden",
			"clip",
			"visible",
			"scroll"
		];
		const scaleOverscroll = () => [
			"auto",
			"contain",
			"none"
		];
		const scaleUnambiguousSpacing = () => [
			isArbitraryVariable,
			isArbitraryValue,
			themeSpacing
		];
		const scaleInset = () => [
			isFraction,
			"full",
			"auto",
			...scaleUnambiguousSpacing()
		];
		const scaleGridTemplateColsRows = () => [
			isInteger,
			"none",
			"subgrid",
			isArbitraryVariable,
			isArbitraryValue
		];
		const scaleGridColRowStartAndEnd = () => [
			"auto",
			{ span: [
				"full",
				isInteger,
				isArbitraryVariable,
				isArbitraryValue
			] },
			isInteger,
			isArbitraryVariable,
			isArbitraryValue
		];
		const scaleGridColRowStartOrEnd = () => [
			isInteger,
			"auto",
			isArbitraryVariable,
			isArbitraryValue
		];
		const scaleGridAutoColsRows = () => [
			"auto",
			"min",
			"max",
			"fr",
			isArbitraryVariable,
			isArbitraryValue
		];
		const scaleAlignPrimaryAxis = () => [
			"start",
			"end",
			"center",
			"between",
			"around",
			"evenly",
			"stretch",
			"baseline",
			"center-safe",
			"end-safe"
		];
		const scaleAlignSecondaryAxis = () => [
			"start",
			"end",
			"center",
			"stretch",
			"center-safe",
			"end-safe"
		];
		const scaleMargin = () => ["auto", ...scaleUnambiguousSpacing()];
		const scaleSizing = () => [
			isFraction,
			"auto",
			"full",
			"dvw",
			"dvh",
			"lvw",
			"lvh",
			"svw",
			"svh",
			"min",
			"max",
			"fit",
			...scaleUnambiguousSpacing()
		];
		const scaleSizingInline = () => [
			isFraction,
			"screen",
			"full",
			"dvw",
			"lvw",
			"svw",
			"min",
			"max",
			"fit",
			...scaleUnambiguousSpacing()
		];
		const scaleSizingBlock = () => [
			isFraction,
			"screen",
			"full",
			"lh",
			"dvh",
			"lvh",
			"svh",
			"min",
			"max",
			"fit",
			...scaleUnambiguousSpacing()
		];
		const scaleColor = () => [
			themeColor,
			isArbitraryVariable,
			isArbitraryValue
		];
		const scaleBgPosition = () => [
			...scalePosition(),
			isArbitraryVariablePosition,
			isArbitraryPosition,
			{ position: [isArbitraryVariable, isArbitraryValue] }
		];
		const scaleBgRepeat = () => ["no-repeat", { repeat: [
			"",
			"x",
			"y",
			"space",
			"round"
		] }];
		const scaleBgSize = () => [
			"auto",
			"cover",
			"contain",
			isArbitraryVariableSize,
			isArbitrarySize,
			{ size: [isArbitraryVariable, isArbitraryValue] }
		];
		const scaleGradientStopPosition = () => [
			isPercent,
			isArbitraryVariableLength,
			isArbitraryLength
		];
		const scaleRadius = () => [
			"",
			"none",
			"full",
			themeRadius,
			isArbitraryVariable,
			isArbitraryValue
		];
		const scaleBorderWidth = () => [
			"",
			isNumber,
			isArbitraryVariableLength,
			isArbitraryLength
		];
		const scaleLineStyle = () => [
			"solid",
			"dashed",
			"dotted",
			"double"
		];
		const scaleBlendMode = () => [
			"normal",
			"multiply",
			"screen",
			"overlay",
			"darken",
			"lighten",
			"color-dodge",
			"color-burn",
			"hard-light",
			"soft-light",
			"difference",
			"exclusion",
			"hue",
			"saturation",
			"color",
			"luminosity"
		];
		const scaleMaskImagePosition = () => [
			isNumber,
			isPercent,
			isArbitraryVariablePosition,
			isArbitraryPosition
		];
		const scaleBlur = () => [
			"",
			"none",
			themeBlur,
			isArbitraryVariable,
			isArbitraryValue
		];
		const scaleRotate = () => [
			"none",
			isNumber,
			isArbitraryVariable,
			isArbitraryValue
		];
		const scaleScale = () => [
			"none",
			isNumber,
			isArbitraryVariable,
			isArbitraryValue
		];
		const scaleSkew = () => [
			isNumber,
			isArbitraryVariable,
			isArbitraryValue
		];
		const scaleTranslate = () => [
			isFraction,
			"full",
			...scaleUnambiguousSpacing()
		];
		return {
			cacheSize: 500,
			theme: {
				animate: [
					"spin",
					"ping",
					"pulse",
					"bounce"
				],
				aspect: ["video"],
				blur: [isTshirtSize],
				breakpoint: [isTshirtSize],
				color: [isAny],
				container: [isTshirtSize],
				"drop-shadow": [isTshirtSize],
				ease: [
					"in",
					"out",
					"in-out"
				],
				font: [isAnyNonArbitrary],
				"font-weight": [
					"thin",
					"extralight",
					"light",
					"normal",
					"medium",
					"semibold",
					"bold",
					"extrabold",
					"black"
				],
				"inset-shadow": [isTshirtSize],
				leading: [
					"none",
					"tight",
					"snug",
					"normal",
					"relaxed",
					"loose"
				],
				perspective: [
					"dramatic",
					"near",
					"normal",
					"midrange",
					"distant",
					"none"
				],
				radius: [isTshirtSize],
				shadow: [isTshirtSize],
				spacing: ["px", isNumber],
				text: [isTshirtSize],
				"text-shadow": [isTshirtSize],
				tracking: [
					"tighter",
					"tight",
					"normal",
					"wide",
					"wider",
					"widest"
				]
			},
			classGroups: {
				/**
				* Aspect Ratio
				* @see https://tailwindcss.com/docs/aspect-ratio
				*/
				aspect: [{ aspect: [
					"auto",
					"square",
					isFraction,
					isArbitraryValue,
					isArbitraryVariable,
					themeAspect
				] }],
				/**
				* Container
				* @see https://tailwindcss.com/docs/container
				* @deprecated since Tailwind CSS v4.0.0
				*/
				container: ["container"],
				/**
				* Columns
				* @see https://tailwindcss.com/docs/columns
				*/
				columns: [{ columns: [
					isNumber,
					isArbitraryValue,
					isArbitraryVariable,
					themeContainer
				] }],
				/**
				* Break After
				* @see https://tailwindcss.com/docs/break-after
				*/
				"break-after": [{ "break-after": scaleBreak() }],
				/**
				* Break Before
				* @see https://tailwindcss.com/docs/break-before
				*/
				"break-before": [{ "break-before": scaleBreak() }],
				/**
				* Break Inside
				* @see https://tailwindcss.com/docs/break-inside
				*/
				"break-inside": [{ "break-inside": [
					"auto",
					"avoid",
					"avoid-page",
					"avoid-column"
				] }],
				/**
				* Box Decoration Break
				* @see https://tailwindcss.com/docs/box-decoration-break
				*/
				"box-decoration": [{ "box-decoration": ["slice", "clone"] }],
				/**
				* Box Sizing
				* @see https://tailwindcss.com/docs/box-sizing
				*/
				box: [{ box: ["border", "content"] }],
				/**
				* Display
				* @see https://tailwindcss.com/docs/display
				*/
				display: [
					"block",
					"inline-block",
					"inline",
					"flex",
					"inline-flex",
					"table",
					"inline-table",
					"table-caption",
					"table-cell",
					"table-column",
					"table-column-group",
					"table-footer-group",
					"table-header-group",
					"table-row-group",
					"table-row",
					"flow-root",
					"grid",
					"inline-grid",
					"contents",
					"list-item",
					"hidden"
				],
				/**
				* Screen Reader Only
				* @see https://tailwindcss.com/docs/display#screen-reader-only
				*/
				sr: ["sr-only", "not-sr-only"],
				/**
				* Floats
				* @see https://tailwindcss.com/docs/float
				*/
				float: [{ float: [
					"right",
					"left",
					"none",
					"start",
					"end"
				] }],
				/**
				* Clear
				* @see https://tailwindcss.com/docs/clear
				*/
				clear: [{ clear: [
					"left",
					"right",
					"both",
					"none",
					"start",
					"end"
				] }],
				/**
				* Isolation
				* @see https://tailwindcss.com/docs/isolation
				*/
				isolation: ["isolate", "isolation-auto"],
				/**
				* Object Fit
				* @see https://tailwindcss.com/docs/object-fit
				*/
				"object-fit": [{ object: [
					"contain",
					"cover",
					"fill",
					"none",
					"scale-down"
				] }],
				/**
				* Object Position
				* @see https://tailwindcss.com/docs/object-position
				*/
				"object-position": [{ object: scalePositionWithArbitrary() }],
				/**
				* Overflow
				* @see https://tailwindcss.com/docs/overflow
				*/
				overflow: [{ overflow: scaleOverflow() }],
				/**
				* Overflow X
				* @see https://tailwindcss.com/docs/overflow
				*/
				"overflow-x": [{ "overflow-x": scaleOverflow() }],
				/**
				* Overflow Y
				* @see https://tailwindcss.com/docs/overflow
				*/
				"overflow-y": [{ "overflow-y": scaleOverflow() }],
				/**
				* Overscroll Behavior
				* @see https://tailwindcss.com/docs/overscroll-behavior
				*/
				overscroll: [{ overscroll: scaleOverscroll() }],
				/**
				* Overscroll Behavior X
				* @see https://tailwindcss.com/docs/overscroll-behavior
				*/
				"overscroll-x": [{ "overscroll-x": scaleOverscroll() }],
				/**
				* Overscroll Behavior Y
				* @see https://tailwindcss.com/docs/overscroll-behavior
				*/
				"overscroll-y": [{ "overscroll-y": scaleOverscroll() }],
				/**
				* Position
				* @see https://tailwindcss.com/docs/position
				*/
				position: [
					"static",
					"fixed",
					"absolute",
					"relative",
					"sticky"
				],
				/**
				* Inset
				* @see https://tailwindcss.com/docs/top-right-bottom-left
				*/
				inset: [{ inset: scaleInset() }],
				/**
				* Inset Inline
				* @see https://tailwindcss.com/docs/top-right-bottom-left
				*/
				"inset-x": [{ "inset-x": scaleInset() }],
				/**
				* Inset Block
				* @see https://tailwindcss.com/docs/top-right-bottom-left
				*/
				"inset-y": [{ "inset-y": scaleInset() }],
				/**
				* Inset Inline Start
				* @see https://tailwindcss.com/docs/top-right-bottom-left
				* @todo class group will be renamed to `inset-s` in next major release
				*/
				start: [{
					"inset-s": scaleInset(),
					/**
					* @deprecated since Tailwind CSS v4.2.0 in favor of `inset-s-*` utilities.
					* @see https://github.com/tailwindlabs/tailwindcss/pull/19613
					*/
					start: scaleInset()
				}],
				/**
				* Inset Inline End
				* @see https://tailwindcss.com/docs/top-right-bottom-left
				* @todo class group will be renamed to `inset-e` in next major release
				*/
				end: [{
					"inset-e": scaleInset(),
					/**
					* @deprecated since Tailwind CSS v4.2.0 in favor of `inset-e-*` utilities.
					* @see https://github.com/tailwindlabs/tailwindcss/pull/19613
					*/
					end: scaleInset()
				}],
				/**
				* Inset Block Start
				* @see https://tailwindcss.com/docs/top-right-bottom-left
				*/
				"inset-bs": [{ "inset-bs": scaleInset() }],
				/**
				* Inset Block End
				* @see https://tailwindcss.com/docs/top-right-bottom-left
				*/
				"inset-be": [{ "inset-be": scaleInset() }],
				/**
				* Top
				* @see https://tailwindcss.com/docs/top-right-bottom-left
				*/
				top: [{ top: scaleInset() }],
				/**
				* Right
				* @see https://tailwindcss.com/docs/top-right-bottom-left
				*/
				right: [{ right: scaleInset() }],
				/**
				* Bottom
				* @see https://tailwindcss.com/docs/top-right-bottom-left
				*/
				bottom: [{ bottom: scaleInset() }],
				/**
				* Left
				* @see https://tailwindcss.com/docs/top-right-bottom-left
				*/
				left: [{ left: scaleInset() }],
				/**
				* Visibility
				* @see https://tailwindcss.com/docs/visibility
				*/
				visibility: [
					"visible",
					"invisible",
					"collapse"
				],
				/**
				* Z-Index
				* @see https://tailwindcss.com/docs/z-index
				*/
				z: [{ z: [
					isInteger,
					"auto",
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Flex Basis
				* @see https://tailwindcss.com/docs/flex-basis
				*/
				basis: [{ basis: [
					isFraction,
					"full",
					"auto",
					themeContainer,
					...scaleUnambiguousSpacing()
				] }],
				/**
				* Flex Direction
				* @see https://tailwindcss.com/docs/flex-direction
				*/
				"flex-direction": [{ flex: [
					"row",
					"row-reverse",
					"col",
					"col-reverse"
				] }],
				/**
				* Flex Wrap
				* @see https://tailwindcss.com/docs/flex-wrap
				*/
				"flex-wrap": [{ flex: [
					"nowrap",
					"wrap",
					"wrap-reverse"
				] }],
				/**
				* Flex
				* @see https://tailwindcss.com/docs/flex
				*/
				flex: [{ flex: [
					isNumber,
					isFraction,
					"auto",
					"initial",
					"none",
					isArbitraryValue
				] }],
				/**
				* Flex Grow
				* @see https://tailwindcss.com/docs/flex-grow
				*/
				grow: [{ grow: [
					"",
					isNumber,
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Flex Shrink
				* @see https://tailwindcss.com/docs/flex-shrink
				*/
				shrink: [{ shrink: [
					"",
					isNumber,
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Order
				* @see https://tailwindcss.com/docs/order
				*/
				order: [{ order: [
					isInteger,
					"first",
					"last",
					"none",
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Grid Template Columns
				* @see https://tailwindcss.com/docs/grid-template-columns
				*/
				"grid-cols": [{ "grid-cols": scaleGridTemplateColsRows() }],
				/**
				* Grid Column Start / End
				* @see https://tailwindcss.com/docs/grid-column
				*/
				"col-start-end": [{ col: scaleGridColRowStartAndEnd() }],
				/**
				* Grid Column Start
				* @see https://tailwindcss.com/docs/grid-column
				*/
				"col-start": [{ "col-start": scaleGridColRowStartOrEnd() }],
				/**
				* Grid Column End
				* @see https://tailwindcss.com/docs/grid-column
				*/
				"col-end": [{ "col-end": scaleGridColRowStartOrEnd() }],
				/**
				* Grid Template Rows
				* @see https://tailwindcss.com/docs/grid-template-rows
				*/
				"grid-rows": [{ "grid-rows": scaleGridTemplateColsRows() }],
				/**
				* Grid Row Start / End
				* @see https://tailwindcss.com/docs/grid-row
				*/
				"row-start-end": [{ row: scaleGridColRowStartAndEnd() }],
				/**
				* Grid Row Start
				* @see https://tailwindcss.com/docs/grid-row
				*/
				"row-start": [{ "row-start": scaleGridColRowStartOrEnd() }],
				/**
				* Grid Row End
				* @see https://tailwindcss.com/docs/grid-row
				*/
				"row-end": [{ "row-end": scaleGridColRowStartOrEnd() }],
				/**
				* Grid Auto Flow
				* @see https://tailwindcss.com/docs/grid-auto-flow
				*/
				"grid-flow": [{ "grid-flow": [
					"row",
					"col",
					"dense",
					"row-dense",
					"col-dense"
				] }],
				/**
				* Grid Auto Columns
				* @see https://tailwindcss.com/docs/grid-auto-columns
				*/
				"auto-cols": [{ "auto-cols": scaleGridAutoColsRows() }],
				/**
				* Grid Auto Rows
				* @see https://tailwindcss.com/docs/grid-auto-rows
				*/
				"auto-rows": [{ "auto-rows": scaleGridAutoColsRows() }],
				/**
				* Gap
				* @see https://tailwindcss.com/docs/gap
				*/
				gap: [{ gap: scaleUnambiguousSpacing() }],
				/**
				* Gap X
				* @see https://tailwindcss.com/docs/gap
				*/
				"gap-x": [{ "gap-x": scaleUnambiguousSpacing() }],
				/**
				* Gap Y
				* @see https://tailwindcss.com/docs/gap
				*/
				"gap-y": [{ "gap-y": scaleUnambiguousSpacing() }],
				/**
				* Justify Content
				* @see https://tailwindcss.com/docs/justify-content
				*/
				"justify-content": [{ justify: [...scaleAlignPrimaryAxis(), "normal"] }],
				/**
				* Justify Items
				* @see https://tailwindcss.com/docs/justify-items
				*/
				"justify-items": [{ "justify-items": [...scaleAlignSecondaryAxis(), "normal"] }],
				/**
				* Justify Self
				* @see https://tailwindcss.com/docs/justify-self
				*/
				"justify-self": [{ "justify-self": ["auto", ...scaleAlignSecondaryAxis()] }],
				/**
				* Align Content
				* @see https://tailwindcss.com/docs/align-content
				*/
				"align-content": [{ content: ["normal", ...scaleAlignPrimaryAxis()] }],
				/**
				* Align Items
				* @see https://tailwindcss.com/docs/align-items
				*/
				"align-items": [{ items: [...scaleAlignSecondaryAxis(), { baseline: ["", "last"] }] }],
				/**
				* Align Self
				* @see https://tailwindcss.com/docs/align-self
				*/
				"align-self": [{ self: [
					"auto",
					...scaleAlignSecondaryAxis(),
					{ baseline: ["", "last"] }
				] }],
				/**
				* Place Content
				* @see https://tailwindcss.com/docs/place-content
				*/
				"place-content": [{ "place-content": scaleAlignPrimaryAxis() }],
				/**
				* Place Items
				* @see https://tailwindcss.com/docs/place-items
				*/
				"place-items": [{ "place-items": [...scaleAlignSecondaryAxis(), "baseline"] }],
				/**
				* Place Self
				* @see https://tailwindcss.com/docs/place-self
				*/
				"place-self": [{ "place-self": ["auto", ...scaleAlignSecondaryAxis()] }],
				/**
				* Padding
				* @see https://tailwindcss.com/docs/padding
				*/
				p: [{ p: scaleUnambiguousSpacing() }],
				/**
				* Padding Inline
				* @see https://tailwindcss.com/docs/padding
				*/
				px: [{ px: scaleUnambiguousSpacing() }],
				/**
				* Padding Block
				* @see https://tailwindcss.com/docs/padding
				*/
				py: [{ py: scaleUnambiguousSpacing() }],
				/**
				* Padding Inline Start
				* @see https://tailwindcss.com/docs/padding
				*/
				ps: [{ ps: scaleUnambiguousSpacing() }],
				/**
				* Padding Inline End
				* @see https://tailwindcss.com/docs/padding
				*/
				pe: [{ pe: scaleUnambiguousSpacing() }],
				/**
				* Padding Block Start
				* @see https://tailwindcss.com/docs/padding
				*/
				pbs: [{ pbs: scaleUnambiguousSpacing() }],
				/**
				* Padding Block End
				* @see https://tailwindcss.com/docs/padding
				*/
				pbe: [{ pbe: scaleUnambiguousSpacing() }],
				/**
				* Padding Top
				* @see https://tailwindcss.com/docs/padding
				*/
				pt: [{ pt: scaleUnambiguousSpacing() }],
				/**
				* Padding Right
				* @see https://tailwindcss.com/docs/padding
				*/
				pr: [{ pr: scaleUnambiguousSpacing() }],
				/**
				* Padding Bottom
				* @see https://tailwindcss.com/docs/padding
				*/
				pb: [{ pb: scaleUnambiguousSpacing() }],
				/**
				* Padding Left
				* @see https://tailwindcss.com/docs/padding
				*/
				pl: [{ pl: scaleUnambiguousSpacing() }],
				/**
				* Margin
				* @see https://tailwindcss.com/docs/margin
				*/
				m: [{ m: scaleMargin() }],
				/**
				* Margin Inline
				* @see https://tailwindcss.com/docs/margin
				*/
				mx: [{ mx: scaleMargin() }],
				/**
				* Margin Block
				* @see https://tailwindcss.com/docs/margin
				*/
				my: [{ my: scaleMargin() }],
				/**
				* Margin Inline Start
				* @see https://tailwindcss.com/docs/margin
				*/
				ms: [{ ms: scaleMargin() }],
				/**
				* Margin Inline End
				* @see https://tailwindcss.com/docs/margin
				*/
				me: [{ me: scaleMargin() }],
				/**
				* Margin Block Start
				* @see https://tailwindcss.com/docs/margin
				*/
				mbs: [{ mbs: scaleMargin() }],
				/**
				* Margin Block End
				* @see https://tailwindcss.com/docs/margin
				*/
				mbe: [{ mbe: scaleMargin() }],
				/**
				* Margin Top
				* @see https://tailwindcss.com/docs/margin
				*/
				mt: [{ mt: scaleMargin() }],
				/**
				* Margin Right
				* @see https://tailwindcss.com/docs/margin
				*/
				mr: [{ mr: scaleMargin() }],
				/**
				* Margin Bottom
				* @see https://tailwindcss.com/docs/margin
				*/
				mb: [{ mb: scaleMargin() }],
				/**
				* Margin Left
				* @see https://tailwindcss.com/docs/margin
				*/
				ml: [{ ml: scaleMargin() }],
				/**
				* Space Between X
				* @see https://tailwindcss.com/docs/margin#adding-space-between-children
				*/
				"space-x": [{ "space-x": scaleUnambiguousSpacing() }],
				/**
				* Space Between X Reverse
				* @see https://tailwindcss.com/docs/margin#adding-space-between-children
				*/
				"space-x-reverse": ["space-x-reverse"],
				/**
				* Space Between Y
				* @see https://tailwindcss.com/docs/margin#adding-space-between-children
				*/
				"space-y": [{ "space-y": scaleUnambiguousSpacing() }],
				/**
				* Space Between Y Reverse
				* @see https://tailwindcss.com/docs/margin#adding-space-between-children
				*/
				"space-y-reverse": ["space-y-reverse"],
				/**
				* Size
				* @see https://tailwindcss.com/docs/width#setting-both-width-and-height
				*/
				size: [{ size: scaleSizing() }],
				/**
				* Inline Size
				* @see https://tailwindcss.com/docs/width
				*/
				"inline-size": [{ inline: ["auto", ...scaleSizingInline()] }],
				/**
				* Min-Inline Size
				* @see https://tailwindcss.com/docs/min-width
				*/
				"min-inline-size": [{ "min-inline": ["auto", ...scaleSizingInline()] }],
				/**
				* Max-Inline Size
				* @see https://tailwindcss.com/docs/max-width
				*/
				"max-inline-size": [{ "max-inline": ["none", ...scaleSizingInline()] }],
				/**
				* Block Size
				* @see https://tailwindcss.com/docs/height
				*/
				"block-size": [{ block: ["auto", ...scaleSizingBlock()] }],
				/**
				* Min-Block Size
				* @see https://tailwindcss.com/docs/min-height
				*/
				"min-block-size": [{ "min-block": ["auto", ...scaleSizingBlock()] }],
				/**
				* Max-Block Size
				* @see https://tailwindcss.com/docs/max-height
				*/
				"max-block-size": [{ "max-block": ["none", ...scaleSizingBlock()] }],
				/**
				* Width
				* @see https://tailwindcss.com/docs/width
				*/
				w: [{ w: [
					themeContainer,
					"screen",
					...scaleSizing()
				] }],
				/**
				* Min-Width
				* @see https://tailwindcss.com/docs/min-width
				*/
				"min-w": [{ "min-w": [
					themeContainer,
					"screen",
					"none",
					...scaleSizing()
				] }],
				/**
				* Max-Width
				* @see https://tailwindcss.com/docs/max-width
				*/
				"max-w": [{ "max-w": [
					themeContainer,
					"screen",
					"none",
					"prose",
					{ screen: [themeBreakpoint] },
					...scaleSizing()
				] }],
				/**
				* Height
				* @see https://tailwindcss.com/docs/height
				*/
				h: [{ h: [
					"screen",
					"lh",
					...scaleSizing()
				] }],
				/**
				* Min-Height
				* @see https://tailwindcss.com/docs/min-height
				*/
				"min-h": [{ "min-h": [
					"screen",
					"lh",
					"none",
					...scaleSizing()
				] }],
				/**
				* Max-Height
				* @see https://tailwindcss.com/docs/max-height
				*/
				"max-h": [{ "max-h": [
					"screen",
					"lh",
					...scaleSizing()
				] }],
				/**
				* Font Size
				* @see https://tailwindcss.com/docs/font-size
				*/
				"font-size": [{ text: [
					"base",
					themeText,
					isArbitraryVariableLength,
					isArbitraryLength
				] }],
				/**
				* Font Smoothing
				* @see https://tailwindcss.com/docs/font-smoothing
				*/
				"font-smoothing": ["antialiased", "subpixel-antialiased"],
				/**
				* Font Style
				* @see https://tailwindcss.com/docs/font-style
				*/
				"font-style": ["italic", "not-italic"],
				/**
				* Font Weight
				* @see https://tailwindcss.com/docs/font-weight
				*/
				"font-weight": [{ font: [
					themeFontWeight,
					isArbitraryVariableWeight,
					isArbitraryWeight
				] }],
				/**
				* Font Stretch
				* @see https://tailwindcss.com/docs/font-stretch
				*/
				"font-stretch": [{ "font-stretch": [
					"ultra-condensed",
					"extra-condensed",
					"condensed",
					"semi-condensed",
					"normal",
					"semi-expanded",
					"expanded",
					"extra-expanded",
					"ultra-expanded",
					isPercent,
					isArbitraryValue
				] }],
				/**
				* Font Family
				* @see https://tailwindcss.com/docs/font-family
				*/
				"font-family": [{ font: [
					isArbitraryVariableFamilyName,
					isArbitraryFamilyName,
					themeFont
				] }],
				/**
				* Font Feature Settings
				* @see https://tailwindcss.com/docs/font-feature-settings
				*/
				"font-features": [{ "font-features": [isArbitraryValue] }],
				/**
				* Font Variant Numeric
				* @see https://tailwindcss.com/docs/font-variant-numeric
				*/
				"fvn-normal": ["normal-nums"],
				/**
				* Font Variant Numeric
				* @see https://tailwindcss.com/docs/font-variant-numeric
				*/
				"fvn-ordinal": ["ordinal"],
				/**
				* Font Variant Numeric
				* @see https://tailwindcss.com/docs/font-variant-numeric
				*/
				"fvn-slashed-zero": ["slashed-zero"],
				/**
				* Font Variant Numeric
				* @see https://tailwindcss.com/docs/font-variant-numeric
				*/
				"fvn-figure": ["lining-nums", "oldstyle-nums"],
				/**
				* Font Variant Numeric
				* @see https://tailwindcss.com/docs/font-variant-numeric
				*/
				"fvn-spacing": ["proportional-nums", "tabular-nums"],
				/**
				* Font Variant Numeric
				* @see https://tailwindcss.com/docs/font-variant-numeric
				*/
				"fvn-fraction": ["diagonal-fractions", "stacked-fractions"],
				/**
				* Letter Spacing
				* @see https://tailwindcss.com/docs/letter-spacing
				*/
				tracking: [{ tracking: [
					themeTracking,
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Line Clamp
				* @see https://tailwindcss.com/docs/line-clamp
				*/
				"line-clamp": [{ "line-clamp": [
					isNumber,
					"none",
					isArbitraryVariable,
					isArbitraryNumber
				] }],
				/**
				* Line Height
				* @see https://tailwindcss.com/docs/line-height
				*/
				leading: [{ leading: [themeLeading, ...scaleUnambiguousSpacing()] }],
				/**
				* List Style Image
				* @see https://tailwindcss.com/docs/list-style-image
				*/
				"list-image": [{ "list-image": [
					"none",
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* List Style Position
				* @see https://tailwindcss.com/docs/list-style-position
				*/
				"list-style-position": [{ list: ["inside", "outside"] }],
				/**
				* List Style Type
				* @see https://tailwindcss.com/docs/list-style-type
				*/
				"list-style-type": [{ list: [
					"disc",
					"decimal",
					"none",
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Text Alignment
				* @see https://tailwindcss.com/docs/text-align
				*/
				"text-alignment": [{ text: [
					"left",
					"center",
					"right",
					"justify",
					"start",
					"end"
				] }],
				/**
				* Placeholder Color
				* @deprecated since Tailwind CSS v3.0.0
				* @see https://v3.tailwindcss.com/docs/placeholder-color
				*/
				"placeholder-color": [{ placeholder: scaleColor() }],
				/**
				* Text Color
				* @see https://tailwindcss.com/docs/text-color
				*/
				"text-color": [{ text: scaleColor() }],
				/**
				* Text Decoration
				* @see https://tailwindcss.com/docs/text-decoration
				*/
				"text-decoration": [
					"underline",
					"overline",
					"line-through",
					"no-underline"
				],
				/**
				* Text Decoration Style
				* @see https://tailwindcss.com/docs/text-decoration-style
				*/
				"text-decoration-style": [{ decoration: [...scaleLineStyle(), "wavy"] }],
				/**
				* Text Decoration Thickness
				* @see https://tailwindcss.com/docs/text-decoration-thickness
				*/
				"text-decoration-thickness": [{ decoration: [
					isNumber,
					"from-font",
					"auto",
					isArbitraryVariable,
					isArbitraryLength
				] }],
				/**
				* Text Decoration Color
				* @see https://tailwindcss.com/docs/text-decoration-color
				*/
				"text-decoration-color": [{ decoration: scaleColor() }],
				/**
				* Text Underline Offset
				* @see https://tailwindcss.com/docs/text-underline-offset
				*/
				"underline-offset": [{ "underline-offset": [
					isNumber,
					"auto",
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Text Transform
				* @see https://tailwindcss.com/docs/text-transform
				*/
				"text-transform": [
					"uppercase",
					"lowercase",
					"capitalize",
					"normal-case"
				],
				/**
				* Text Overflow
				* @see https://tailwindcss.com/docs/text-overflow
				*/
				"text-overflow": [
					"truncate",
					"text-ellipsis",
					"text-clip"
				],
				/**
				* Text Wrap
				* @see https://tailwindcss.com/docs/text-wrap
				*/
				"text-wrap": [{ text: [
					"wrap",
					"nowrap",
					"balance",
					"pretty"
				] }],
				/**
				* Text Indent
				* @see https://tailwindcss.com/docs/text-indent
				*/
				indent: [{ indent: scaleUnambiguousSpacing() }],
				/**
				* Vertical Alignment
				* @see https://tailwindcss.com/docs/vertical-align
				*/
				"vertical-align": [{ align: [
					"baseline",
					"top",
					"middle",
					"bottom",
					"text-top",
					"text-bottom",
					"sub",
					"super",
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Whitespace
				* @see https://tailwindcss.com/docs/whitespace
				*/
				whitespace: [{ whitespace: [
					"normal",
					"nowrap",
					"pre",
					"pre-line",
					"pre-wrap",
					"break-spaces"
				] }],
				/**
				* Word Break
				* @see https://tailwindcss.com/docs/word-break
				*/
				break: [{ break: [
					"normal",
					"words",
					"all",
					"keep"
				] }],
				/**
				* Overflow Wrap
				* @see https://tailwindcss.com/docs/overflow-wrap
				*/
				wrap: [{ wrap: [
					"break-word",
					"anywhere",
					"normal"
				] }],
				/**
				* Hyphens
				* @see https://tailwindcss.com/docs/hyphens
				*/
				hyphens: [{ hyphens: [
					"none",
					"manual",
					"auto"
				] }],
				/**
				* Content
				* @see https://tailwindcss.com/docs/content
				*/
				content: [{ content: [
					"none",
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Background Attachment
				* @see https://tailwindcss.com/docs/background-attachment
				*/
				"bg-attachment": [{ bg: [
					"fixed",
					"local",
					"scroll"
				] }],
				/**
				* Background Clip
				* @see https://tailwindcss.com/docs/background-clip
				*/
				"bg-clip": [{ "bg-clip": [
					"border",
					"padding",
					"content",
					"text"
				] }],
				/**
				* Background Origin
				* @see https://tailwindcss.com/docs/background-origin
				*/
				"bg-origin": [{ "bg-origin": [
					"border",
					"padding",
					"content"
				] }],
				/**
				* Background Position
				* @see https://tailwindcss.com/docs/background-position
				*/
				"bg-position": [{ bg: scaleBgPosition() }],
				/**
				* Background Repeat
				* @see https://tailwindcss.com/docs/background-repeat
				*/
				"bg-repeat": [{ bg: scaleBgRepeat() }],
				/**
				* Background Size
				* @see https://tailwindcss.com/docs/background-size
				*/
				"bg-size": [{ bg: scaleBgSize() }],
				/**
				* Background Image
				* @see https://tailwindcss.com/docs/background-image
				*/
				"bg-image": [{ bg: [
					"none",
					{
						linear: [
							{ to: [
								"t",
								"tr",
								"r",
								"br",
								"b",
								"bl",
								"l",
								"tl"
							] },
							isInteger,
							isArbitraryVariable,
							isArbitraryValue
						],
						radial: [
							"",
							isArbitraryVariable,
							isArbitraryValue
						],
						conic: [
							isInteger,
							isArbitraryVariable,
							isArbitraryValue
						]
					},
					isArbitraryVariableImage,
					isArbitraryImage
				] }],
				/**
				* Background Color
				* @see https://tailwindcss.com/docs/background-color
				*/
				"bg-color": [{ bg: scaleColor() }],
				/**
				* Gradient Color Stops From Position
				* @see https://tailwindcss.com/docs/gradient-color-stops
				*/
				"gradient-from-pos": [{ from: scaleGradientStopPosition() }],
				/**
				* Gradient Color Stops Via Position
				* @see https://tailwindcss.com/docs/gradient-color-stops
				*/
				"gradient-via-pos": [{ via: scaleGradientStopPosition() }],
				/**
				* Gradient Color Stops To Position
				* @see https://tailwindcss.com/docs/gradient-color-stops
				*/
				"gradient-to-pos": [{ to: scaleGradientStopPosition() }],
				/**
				* Gradient Color Stops From
				* @see https://tailwindcss.com/docs/gradient-color-stops
				*/
				"gradient-from": [{ from: scaleColor() }],
				/**
				* Gradient Color Stops Via
				* @see https://tailwindcss.com/docs/gradient-color-stops
				*/
				"gradient-via": [{ via: scaleColor() }],
				/**
				* Gradient Color Stops To
				* @see https://tailwindcss.com/docs/gradient-color-stops
				*/
				"gradient-to": [{ to: scaleColor() }],
				/**
				* Border Radius
				* @see https://tailwindcss.com/docs/border-radius
				*/
				rounded: [{ rounded: scaleRadius() }],
				/**
				* Border Radius Start
				* @see https://tailwindcss.com/docs/border-radius
				*/
				"rounded-s": [{ "rounded-s": scaleRadius() }],
				/**
				* Border Radius End
				* @see https://tailwindcss.com/docs/border-radius
				*/
				"rounded-e": [{ "rounded-e": scaleRadius() }],
				/**
				* Border Radius Top
				* @see https://tailwindcss.com/docs/border-radius
				*/
				"rounded-t": [{ "rounded-t": scaleRadius() }],
				/**
				* Border Radius Right
				* @see https://tailwindcss.com/docs/border-radius
				*/
				"rounded-r": [{ "rounded-r": scaleRadius() }],
				/**
				* Border Radius Bottom
				* @see https://tailwindcss.com/docs/border-radius
				*/
				"rounded-b": [{ "rounded-b": scaleRadius() }],
				/**
				* Border Radius Left
				* @see https://tailwindcss.com/docs/border-radius
				*/
				"rounded-l": [{ "rounded-l": scaleRadius() }],
				/**
				* Border Radius Start Start
				* @see https://tailwindcss.com/docs/border-radius
				*/
				"rounded-ss": [{ "rounded-ss": scaleRadius() }],
				/**
				* Border Radius Start End
				* @see https://tailwindcss.com/docs/border-radius
				*/
				"rounded-se": [{ "rounded-se": scaleRadius() }],
				/**
				* Border Radius End End
				* @see https://tailwindcss.com/docs/border-radius
				*/
				"rounded-ee": [{ "rounded-ee": scaleRadius() }],
				/**
				* Border Radius End Start
				* @see https://tailwindcss.com/docs/border-radius
				*/
				"rounded-es": [{ "rounded-es": scaleRadius() }],
				/**
				* Border Radius Top Left
				* @see https://tailwindcss.com/docs/border-radius
				*/
				"rounded-tl": [{ "rounded-tl": scaleRadius() }],
				/**
				* Border Radius Top Right
				* @see https://tailwindcss.com/docs/border-radius
				*/
				"rounded-tr": [{ "rounded-tr": scaleRadius() }],
				/**
				* Border Radius Bottom Right
				* @see https://tailwindcss.com/docs/border-radius
				*/
				"rounded-br": [{ "rounded-br": scaleRadius() }],
				/**
				* Border Radius Bottom Left
				* @see https://tailwindcss.com/docs/border-radius
				*/
				"rounded-bl": [{ "rounded-bl": scaleRadius() }],
				/**
				* Border Width
				* @see https://tailwindcss.com/docs/border-width
				*/
				"border-w": [{ border: scaleBorderWidth() }],
				/**
				* Border Width Inline
				* @see https://tailwindcss.com/docs/border-width
				*/
				"border-w-x": [{ "border-x": scaleBorderWidth() }],
				/**
				* Border Width Block
				* @see https://tailwindcss.com/docs/border-width
				*/
				"border-w-y": [{ "border-y": scaleBorderWidth() }],
				/**
				* Border Width Inline Start
				* @see https://tailwindcss.com/docs/border-width
				*/
				"border-w-s": [{ "border-s": scaleBorderWidth() }],
				/**
				* Border Width Inline End
				* @see https://tailwindcss.com/docs/border-width
				*/
				"border-w-e": [{ "border-e": scaleBorderWidth() }],
				/**
				* Border Width Block Start
				* @see https://tailwindcss.com/docs/border-width
				*/
				"border-w-bs": [{ "border-bs": scaleBorderWidth() }],
				/**
				* Border Width Block End
				* @see https://tailwindcss.com/docs/border-width
				*/
				"border-w-be": [{ "border-be": scaleBorderWidth() }],
				/**
				* Border Width Top
				* @see https://tailwindcss.com/docs/border-width
				*/
				"border-w-t": [{ "border-t": scaleBorderWidth() }],
				/**
				* Border Width Right
				* @see https://tailwindcss.com/docs/border-width
				*/
				"border-w-r": [{ "border-r": scaleBorderWidth() }],
				/**
				* Border Width Bottom
				* @see https://tailwindcss.com/docs/border-width
				*/
				"border-w-b": [{ "border-b": scaleBorderWidth() }],
				/**
				* Border Width Left
				* @see https://tailwindcss.com/docs/border-width
				*/
				"border-w-l": [{ "border-l": scaleBorderWidth() }],
				/**
				* Divide Width X
				* @see https://tailwindcss.com/docs/border-width#between-children
				*/
				"divide-x": [{ "divide-x": scaleBorderWidth() }],
				/**
				* Divide Width X Reverse
				* @see https://tailwindcss.com/docs/border-width#between-children
				*/
				"divide-x-reverse": ["divide-x-reverse"],
				/**
				* Divide Width Y
				* @see https://tailwindcss.com/docs/border-width#between-children
				*/
				"divide-y": [{ "divide-y": scaleBorderWidth() }],
				/**
				* Divide Width Y Reverse
				* @see https://tailwindcss.com/docs/border-width#between-children
				*/
				"divide-y-reverse": ["divide-y-reverse"],
				/**
				* Border Style
				* @see https://tailwindcss.com/docs/border-style
				*/
				"border-style": [{ border: [
					...scaleLineStyle(),
					"hidden",
					"none"
				] }],
				/**
				* Divide Style
				* @see https://tailwindcss.com/docs/border-style#setting-the-divider-style
				*/
				"divide-style": [{ divide: [
					...scaleLineStyle(),
					"hidden",
					"none"
				] }],
				/**
				* Border Color
				* @see https://tailwindcss.com/docs/border-color
				*/
				"border-color": [{ border: scaleColor() }],
				/**
				* Border Color Inline
				* @see https://tailwindcss.com/docs/border-color
				*/
				"border-color-x": [{ "border-x": scaleColor() }],
				/**
				* Border Color Block
				* @see https://tailwindcss.com/docs/border-color
				*/
				"border-color-y": [{ "border-y": scaleColor() }],
				/**
				* Border Color Inline Start
				* @see https://tailwindcss.com/docs/border-color
				*/
				"border-color-s": [{ "border-s": scaleColor() }],
				/**
				* Border Color Inline End
				* @see https://tailwindcss.com/docs/border-color
				*/
				"border-color-e": [{ "border-e": scaleColor() }],
				/**
				* Border Color Block Start
				* @see https://tailwindcss.com/docs/border-color
				*/
				"border-color-bs": [{ "border-bs": scaleColor() }],
				/**
				* Border Color Block End
				* @see https://tailwindcss.com/docs/border-color
				*/
				"border-color-be": [{ "border-be": scaleColor() }],
				/**
				* Border Color Top
				* @see https://tailwindcss.com/docs/border-color
				*/
				"border-color-t": [{ "border-t": scaleColor() }],
				/**
				* Border Color Right
				* @see https://tailwindcss.com/docs/border-color
				*/
				"border-color-r": [{ "border-r": scaleColor() }],
				/**
				* Border Color Bottom
				* @see https://tailwindcss.com/docs/border-color
				*/
				"border-color-b": [{ "border-b": scaleColor() }],
				/**
				* Border Color Left
				* @see https://tailwindcss.com/docs/border-color
				*/
				"border-color-l": [{ "border-l": scaleColor() }],
				/**
				* Divide Color
				* @see https://tailwindcss.com/docs/divide-color
				*/
				"divide-color": [{ divide: scaleColor() }],
				/**
				* Outline Style
				* @see https://tailwindcss.com/docs/outline-style
				*/
				"outline-style": [{ outline: [
					...scaleLineStyle(),
					"none",
					"hidden"
				] }],
				/**
				* Outline Offset
				* @see https://tailwindcss.com/docs/outline-offset
				*/
				"outline-offset": [{ "outline-offset": [
					isNumber,
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Outline Width
				* @see https://tailwindcss.com/docs/outline-width
				*/
				"outline-w": [{ outline: [
					"",
					isNumber,
					isArbitraryVariableLength,
					isArbitraryLength
				] }],
				/**
				* Outline Color
				* @see https://tailwindcss.com/docs/outline-color
				*/
				"outline-color": [{ outline: scaleColor() }],
				/**
				* Box Shadow
				* @see https://tailwindcss.com/docs/box-shadow
				*/
				shadow: [{ shadow: [
					"",
					"none",
					themeShadow,
					isArbitraryVariableShadow,
					isArbitraryShadow
				] }],
				/**
				* Box Shadow Color
				* @see https://tailwindcss.com/docs/box-shadow#setting-the-shadow-color
				*/
				"shadow-color": [{ shadow: scaleColor() }],
				/**
				* Inset Box Shadow
				* @see https://tailwindcss.com/docs/box-shadow#adding-an-inset-shadow
				*/
				"inset-shadow": [{ "inset-shadow": [
					"none",
					themeInsetShadow,
					isArbitraryVariableShadow,
					isArbitraryShadow
				] }],
				/**
				* Inset Box Shadow Color
				* @see https://tailwindcss.com/docs/box-shadow#setting-the-inset-shadow-color
				*/
				"inset-shadow-color": [{ "inset-shadow": scaleColor() }],
				/**
				* Ring Width
				* @see https://tailwindcss.com/docs/box-shadow#adding-a-ring
				*/
				"ring-w": [{ ring: scaleBorderWidth() }],
				/**
				* Ring Width Inset
				* @see https://v3.tailwindcss.com/docs/ring-width#inset-rings
				* @deprecated since Tailwind CSS v4.0.0
				* @see https://github.com/tailwindlabs/tailwindcss/blob/v4.0.0/packages/tailwindcss/src/utilities.ts#L4158
				*/
				"ring-w-inset": ["ring-inset"],
				/**
				* Ring Color
				* @see https://tailwindcss.com/docs/box-shadow#setting-the-ring-color
				*/
				"ring-color": [{ ring: scaleColor() }],
				/**
				* Ring Offset Width
				* @see https://v3.tailwindcss.com/docs/ring-offset-width
				* @deprecated since Tailwind CSS v4.0.0
				* @see https://github.com/tailwindlabs/tailwindcss/blob/v4.0.0/packages/tailwindcss/src/utilities.ts#L4158
				*/
				"ring-offset-w": [{ "ring-offset": [isNumber, isArbitraryLength] }],
				/**
				* Ring Offset Color
				* @see https://v3.tailwindcss.com/docs/ring-offset-color
				* @deprecated since Tailwind CSS v4.0.0
				* @see https://github.com/tailwindlabs/tailwindcss/blob/v4.0.0/packages/tailwindcss/src/utilities.ts#L4158
				*/
				"ring-offset-color": [{ "ring-offset": scaleColor() }],
				/**
				* Inset Ring Width
				* @see https://tailwindcss.com/docs/box-shadow#adding-an-inset-ring
				*/
				"inset-ring-w": [{ "inset-ring": scaleBorderWidth() }],
				/**
				* Inset Ring Color
				* @see https://tailwindcss.com/docs/box-shadow#setting-the-inset-ring-color
				*/
				"inset-ring-color": [{ "inset-ring": scaleColor() }],
				/**
				* Text Shadow
				* @see https://tailwindcss.com/docs/text-shadow
				*/
				"text-shadow": [{ "text-shadow": [
					"none",
					themeTextShadow,
					isArbitraryVariableShadow,
					isArbitraryShadow
				] }],
				/**
				* Text Shadow Color
				* @see https://tailwindcss.com/docs/text-shadow#setting-the-shadow-color
				*/
				"text-shadow-color": [{ "text-shadow": scaleColor() }],
				/**
				* Opacity
				* @see https://tailwindcss.com/docs/opacity
				*/
				opacity: [{ opacity: [
					isNumber,
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Mix Blend Mode
				* @see https://tailwindcss.com/docs/mix-blend-mode
				*/
				"mix-blend": [{ "mix-blend": [
					...scaleBlendMode(),
					"plus-darker",
					"plus-lighter"
				] }],
				/**
				* Background Blend Mode
				* @see https://tailwindcss.com/docs/background-blend-mode
				*/
				"bg-blend": [{ "bg-blend": scaleBlendMode() }],
				/**
				* Mask Clip
				* @see https://tailwindcss.com/docs/mask-clip
				*/
				"mask-clip": [{ "mask-clip": [
					"border",
					"padding",
					"content",
					"fill",
					"stroke",
					"view"
				] }, "mask-no-clip"],
				/**
				* Mask Composite
				* @see https://tailwindcss.com/docs/mask-composite
				*/
				"mask-composite": [{ mask: [
					"add",
					"subtract",
					"intersect",
					"exclude"
				] }],
				/**
				* Mask Image
				* @see https://tailwindcss.com/docs/mask-image
				*/
				"mask-image-linear-pos": [{ "mask-linear": [isNumber] }],
				"mask-image-linear-from-pos": [{ "mask-linear-from": scaleMaskImagePosition() }],
				"mask-image-linear-to-pos": [{ "mask-linear-to": scaleMaskImagePosition() }],
				"mask-image-linear-from-color": [{ "mask-linear-from": scaleColor() }],
				"mask-image-linear-to-color": [{ "mask-linear-to": scaleColor() }],
				"mask-image-t-from-pos": [{ "mask-t-from": scaleMaskImagePosition() }],
				"mask-image-t-to-pos": [{ "mask-t-to": scaleMaskImagePosition() }],
				"mask-image-t-from-color": [{ "mask-t-from": scaleColor() }],
				"mask-image-t-to-color": [{ "mask-t-to": scaleColor() }],
				"mask-image-r-from-pos": [{ "mask-r-from": scaleMaskImagePosition() }],
				"mask-image-r-to-pos": [{ "mask-r-to": scaleMaskImagePosition() }],
				"mask-image-r-from-color": [{ "mask-r-from": scaleColor() }],
				"mask-image-r-to-color": [{ "mask-r-to": scaleColor() }],
				"mask-image-b-from-pos": [{ "mask-b-from": scaleMaskImagePosition() }],
				"mask-image-b-to-pos": [{ "mask-b-to": scaleMaskImagePosition() }],
				"mask-image-b-from-color": [{ "mask-b-from": scaleColor() }],
				"mask-image-b-to-color": [{ "mask-b-to": scaleColor() }],
				"mask-image-l-from-pos": [{ "mask-l-from": scaleMaskImagePosition() }],
				"mask-image-l-to-pos": [{ "mask-l-to": scaleMaskImagePosition() }],
				"mask-image-l-from-color": [{ "mask-l-from": scaleColor() }],
				"mask-image-l-to-color": [{ "mask-l-to": scaleColor() }],
				"mask-image-x-from-pos": [{ "mask-x-from": scaleMaskImagePosition() }],
				"mask-image-x-to-pos": [{ "mask-x-to": scaleMaskImagePosition() }],
				"mask-image-x-from-color": [{ "mask-x-from": scaleColor() }],
				"mask-image-x-to-color": [{ "mask-x-to": scaleColor() }],
				"mask-image-y-from-pos": [{ "mask-y-from": scaleMaskImagePosition() }],
				"mask-image-y-to-pos": [{ "mask-y-to": scaleMaskImagePosition() }],
				"mask-image-y-from-color": [{ "mask-y-from": scaleColor() }],
				"mask-image-y-to-color": [{ "mask-y-to": scaleColor() }],
				"mask-image-radial": [{ "mask-radial": [isArbitraryVariable, isArbitraryValue] }],
				"mask-image-radial-from-pos": [{ "mask-radial-from": scaleMaskImagePosition() }],
				"mask-image-radial-to-pos": [{ "mask-radial-to": scaleMaskImagePosition() }],
				"mask-image-radial-from-color": [{ "mask-radial-from": scaleColor() }],
				"mask-image-radial-to-color": [{ "mask-radial-to": scaleColor() }],
				"mask-image-radial-shape": [{ "mask-radial": ["circle", "ellipse"] }],
				"mask-image-radial-size": [{ "mask-radial": [{
					closest: ["side", "corner"],
					farthest: ["side", "corner"]
				}] }],
				"mask-image-radial-pos": [{ "mask-radial-at": scalePosition() }],
				"mask-image-conic-pos": [{ "mask-conic": [isNumber] }],
				"mask-image-conic-from-pos": [{ "mask-conic-from": scaleMaskImagePosition() }],
				"mask-image-conic-to-pos": [{ "mask-conic-to": scaleMaskImagePosition() }],
				"mask-image-conic-from-color": [{ "mask-conic-from": scaleColor() }],
				"mask-image-conic-to-color": [{ "mask-conic-to": scaleColor() }],
				/**
				* Mask Mode
				* @see https://tailwindcss.com/docs/mask-mode
				*/
				"mask-mode": [{ mask: [
					"alpha",
					"luminance",
					"match"
				] }],
				/**
				* Mask Origin
				* @see https://tailwindcss.com/docs/mask-origin
				*/
				"mask-origin": [{ "mask-origin": [
					"border",
					"padding",
					"content",
					"fill",
					"stroke",
					"view"
				] }],
				/**
				* Mask Position
				* @see https://tailwindcss.com/docs/mask-position
				*/
				"mask-position": [{ mask: scaleBgPosition() }],
				/**
				* Mask Repeat
				* @see https://tailwindcss.com/docs/mask-repeat
				*/
				"mask-repeat": [{ mask: scaleBgRepeat() }],
				/**
				* Mask Size
				* @see https://tailwindcss.com/docs/mask-size
				*/
				"mask-size": [{ mask: scaleBgSize() }],
				/**
				* Mask Type
				* @see https://tailwindcss.com/docs/mask-type
				*/
				"mask-type": [{ "mask-type": ["alpha", "luminance"] }],
				/**
				* Mask Image
				* @see https://tailwindcss.com/docs/mask-image
				*/
				"mask-image": [{ mask: [
					"none",
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Filter
				* @see https://tailwindcss.com/docs/filter
				*/
				filter: [{ filter: [
					"",
					"none",
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Blur
				* @see https://tailwindcss.com/docs/blur
				*/
				blur: [{ blur: scaleBlur() }],
				/**
				* Brightness
				* @see https://tailwindcss.com/docs/brightness
				*/
				brightness: [{ brightness: [
					isNumber,
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Contrast
				* @see https://tailwindcss.com/docs/contrast
				*/
				contrast: [{ contrast: [
					isNumber,
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Drop Shadow
				* @see https://tailwindcss.com/docs/drop-shadow
				*/
				"drop-shadow": [{ "drop-shadow": [
					"",
					"none",
					themeDropShadow,
					isArbitraryVariableShadow,
					isArbitraryShadow
				] }],
				/**
				* Drop Shadow Color
				* @see https://tailwindcss.com/docs/filter-drop-shadow#setting-the-shadow-color
				*/
				"drop-shadow-color": [{ "drop-shadow": scaleColor() }],
				/**
				* Grayscale
				* @see https://tailwindcss.com/docs/grayscale
				*/
				grayscale: [{ grayscale: [
					"",
					isNumber,
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Hue Rotate
				* @see https://tailwindcss.com/docs/hue-rotate
				*/
				"hue-rotate": [{ "hue-rotate": [
					isNumber,
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Invert
				* @see https://tailwindcss.com/docs/invert
				*/
				invert: [{ invert: [
					"",
					isNumber,
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Saturate
				* @see https://tailwindcss.com/docs/saturate
				*/
				saturate: [{ saturate: [
					isNumber,
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Sepia
				* @see https://tailwindcss.com/docs/sepia
				*/
				sepia: [{ sepia: [
					"",
					isNumber,
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Backdrop Filter
				* @see https://tailwindcss.com/docs/backdrop-filter
				*/
				"backdrop-filter": [{ "backdrop-filter": [
					"",
					"none",
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Backdrop Blur
				* @see https://tailwindcss.com/docs/backdrop-blur
				*/
				"backdrop-blur": [{ "backdrop-blur": scaleBlur() }],
				/**
				* Backdrop Brightness
				* @see https://tailwindcss.com/docs/backdrop-brightness
				*/
				"backdrop-brightness": [{ "backdrop-brightness": [
					isNumber,
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Backdrop Contrast
				* @see https://tailwindcss.com/docs/backdrop-contrast
				*/
				"backdrop-contrast": [{ "backdrop-contrast": [
					isNumber,
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Backdrop Grayscale
				* @see https://tailwindcss.com/docs/backdrop-grayscale
				*/
				"backdrop-grayscale": [{ "backdrop-grayscale": [
					"",
					isNumber,
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Backdrop Hue Rotate
				* @see https://tailwindcss.com/docs/backdrop-hue-rotate
				*/
				"backdrop-hue-rotate": [{ "backdrop-hue-rotate": [
					isNumber,
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Backdrop Invert
				* @see https://tailwindcss.com/docs/backdrop-invert
				*/
				"backdrop-invert": [{ "backdrop-invert": [
					"",
					isNumber,
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Backdrop Opacity
				* @see https://tailwindcss.com/docs/backdrop-opacity
				*/
				"backdrop-opacity": [{ "backdrop-opacity": [
					isNumber,
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Backdrop Saturate
				* @see https://tailwindcss.com/docs/backdrop-saturate
				*/
				"backdrop-saturate": [{ "backdrop-saturate": [
					isNumber,
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Backdrop Sepia
				* @see https://tailwindcss.com/docs/backdrop-sepia
				*/
				"backdrop-sepia": [{ "backdrop-sepia": [
					"",
					isNumber,
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Border Collapse
				* @see https://tailwindcss.com/docs/border-collapse
				*/
				"border-collapse": [{ border: ["collapse", "separate"] }],
				/**
				* Border Spacing
				* @see https://tailwindcss.com/docs/border-spacing
				*/
				"border-spacing": [{ "border-spacing": scaleUnambiguousSpacing() }],
				/**
				* Border Spacing X
				* @see https://tailwindcss.com/docs/border-spacing
				*/
				"border-spacing-x": [{ "border-spacing-x": scaleUnambiguousSpacing() }],
				/**
				* Border Spacing Y
				* @see https://tailwindcss.com/docs/border-spacing
				*/
				"border-spacing-y": [{ "border-spacing-y": scaleUnambiguousSpacing() }],
				/**
				* Table Layout
				* @see https://tailwindcss.com/docs/table-layout
				*/
				"table-layout": [{ table: ["auto", "fixed"] }],
				/**
				* Caption Side
				* @see https://tailwindcss.com/docs/caption-side
				*/
				caption: [{ caption: ["top", "bottom"] }],
				/**
				* Transition Property
				* @see https://tailwindcss.com/docs/transition-property
				*/
				transition: [{ transition: [
					"",
					"all",
					"colors",
					"opacity",
					"shadow",
					"transform",
					"none",
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Transition Behavior
				* @see https://tailwindcss.com/docs/transition-behavior
				*/
				"transition-behavior": [{ transition: ["normal", "discrete"] }],
				/**
				* Transition Duration
				* @see https://tailwindcss.com/docs/transition-duration
				*/
				duration: [{ duration: [
					isNumber,
					"initial",
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Transition Timing Function
				* @see https://tailwindcss.com/docs/transition-timing-function
				*/
				ease: [{ ease: [
					"linear",
					"initial",
					themeEase,
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Transition Delay
				* @see https://tailwindcss.com/docs/transition-delay
				*/
				delay: [{ delay: [
					isNumber,
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Animation
				* @see https://tailwindcss.com/docs/animation
				*/
				animate: [{ animate: [
					"none",
					themeAnimate,
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Backface Visibility
				* @see https://tailwindcss.com/docs/backface-visibility
				*/
				backface: [{ backface: ["hidden", "visible"] }],
				/**
				* Perspective
				* @see https://tailwindcss.com/docs/perspective
				*/
				perspective: [{ perspective: [
					themePerspective,
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Perspective Origin
				* @see https://tailwindcss.com/docs/perspective-origin
				*/
				"perspective-origin": [{ "perspective-origin": scalePositionWithArbitrary() }],
				/**
				* Rotate
				* @see https://tailwindcss.com/docs/rotate
				*/
				rotate: [{ rotate: scaleRotate() }],
				/**
				* Rotate X
				* @see https://tailwindcss.com/docs/rotate
				*/
				"rotate-x": [{ "rotate-x": scaleRotate() }],
				/**
				* Rotate Y
				* @see https://tailwindcss.com/docs/rotate
				*/
				"rotate-y": [{ "rotate-y": scaleRotate() }],
				/**
				* Rotate Z
				* @see https://tailwindcss.com/docs/rotate
				*/
				"rotate-z": [{ "rotate-z": scaleRotate() }],
				/**
				* Scale
				* @see https://tailwindcss.com/docs/scale
				*/
				scale: [{ scale: scaleScale() }],
				/**
				* Scale X
				* @see https://tailwindcss.com/docs/scale
				*/
				"scale-x": [{ "scale-x": scaleScale() }],
				/**
				* Scale Y
				* @see https://tailwindcss.com/docs/scale
				*/
				"scale-y": [{ "scale-y": scaleScale() }],
				/**
				* Scale Z
				* @see https://tailwindcss.com/docs/scale
				*/
				"scale-z": [{ "scale-z": scaleScale() }],
				/**
				* Scale 3D
				* @see https://tailwindcss.com/docs/scale
				*/
				"scale-3d": ["scale-3d"],
				/**
				* Skew
				* @see https://tailwindcss.com/docs/skew
				*/
				skew: [{ skew: scaleSkew() }],
				/**
				* Skew X
				* @see https://tailwindcss.com/docs/skew
				*/
				"skew-x": [{ "skew-x": scaleSkew() }],
				/**
				* Skew Y
				* @see https://tailwindcss.com/docs/skew
				*/
				"skew-y": [{ "skew-y": scaleSkew() }],
				/**
				* Transform
				* @see https://tailwindcss.com/docs/transform
				*/
				transform: [{ transform: [
					isArbitraryVariable,
					isArbitraryValue,
					"",
					"none",
					"gpu",
					"cpu"
				] }],
				/**
				* Transform Origin
				* @see https://tailwindcss.com/docs/transform-origin
				*/
				"transform-origin": [{ origin: scalePositionWithArbitrary() }],
				/**
				* Transform Style
				* @see https://tailwindcss.com/docs/transform-style
				*/
				"transform-style": [{ transform: ["3d", "flat"] }],
				/**
				* Translate
				* @see https://tailwindcss.com/docs/translate
				*/
				translate: [{ translate: scaleTranslate() }],
				/**
				* Translate X
				* @see https://tailwindcss.com/docs/translate
				*/
				"translate-x": [{ "translate-x": scaleTranslate() }],
				/**
				* Translate Y
				* @see https://tailwindcss.com/docs/translate
				*/
				"translate-y": [{ "translate-y": scaleTranslate() }],
				/**
				* Translate Z
				* @see https://tailwindcss.com/docs/translate
				*/
				"translate-z": [{ "translate-z": scaleTranslate() }],
				/**
				* Translate None
				* @see https://tailwindcss.com/docs/translate
				*/
				"translate-none": ["translate-none"],
				/**
				* Accent Color
				* @see https://tailwindcss.com/docs/accent-color
				*/
				accent: [{ accent: scaleColor() }],
				/**
				* Appearance
				* @see https://tailwindcss.com/docs/appearance
				*/
				appearance: [{ appearance: ["none", "auto"] }],
				/**
				* Caret Color
				* @see https://tailwindcss.com/docs/just-in-time-mode#caret-color-utilities
				*/
				"caret-color": [{ caret: scaleColor() }],
				/**
				* Color Scheme
				* @see https://tailwindcss.com/docs/color-scheme
				*/
				"color-scheme": [{ scheme: [
					"normal",
					"dark",
					"light",
					"light-dark",
					"only-dark",
					"only-light"
				] }],
				/**
				* Cursor
				* @see https://tailwindcss.com/docs/cursor
				*/
				cursor: [{ cursor: [
					"auto",
					"default",
					"pointer",
					"wait",
					"text",
					"move",
					"help",
					"not-allowed",
					"none",
					"context-menu",
					"progress",
					"cell",
					"crosshair",
					"vertical-text",
					"alias",
					"copy",
					"no-drop",
					"grab",
					"grabbing",
					"all-scroll",
					"col-resize",
					"row-resize",
					"n-resize",
					"e-resize",
					"s-resize",
					"w-resize",
					"ne-resize",
					"nw-resize",
					"se-resize",
					"sw-resize",
					"ew-resize",
					"ns-resize",
					"nesw-resize",
					"nwse-resize",
					"zoom-in",
					"zoom-out",
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Field Sizing
				* @see https://tailwindcss.com/docs/field-sizing
				*/
				"field-sizing": [{ "field-sizing": ["fixed", "content"] }],
				/**
				* Pointer Events
				* @see https://tailwindcss.com/docs/pointer-events
				*/
				"pointer-events": [{ "pointer-events": ["auto", "none"] }],
				/**
				* Resize
				* @see https://tailwindcss.com/docs/resize
				*/
				resize: [{ resize: [
					"none",
					"",
					"y",
					"x"
				] }],
				/**
				* Scroll Behavior
				* @see https://tailwindcss.com/docs/scroll-behavior
				*/
				"scroll-behavior": [{ scroll: ["auto", "smooth"] }],
				/**
				* Scroll Margin
				* @see https://tailwindcss.com/docs/scroll-margin
				*/
				"scroll-m": [{ "scroll-m": scaleUnambiguousSpacing() }],
				/**
				* Scroll Margin Inline
				* @see https://tailwindcss.com/docs/scroll-margin
				*/
				"scroll-mx": [{ "scroll-mx": scaleUnambiguousSpacing() }],
				/**
				* Scroll Margin Block
				* @see https://tailwindcss.com/docs/scroll-margin
				*/
				"scroll-my": [{ "scroll-my": scaleUnambiguousSpacing() }],
				/**
				* Scroll Margin Inline Start
				* @see https://tailwindcss.com/docs/scroll-margin
				*/
				"scroll-ms": [{ "scroll-ms": scaleUnambiguousSpacing() }],
				/**
				* Scroll Margin Inline End
				* @see https://tailwindcss.com/docs/scroll-margin
				*/
				"scroll-me": [{ "scroll-me": scaleUnambiguousSpacing() }],
				/**
				* Scroll Margin Block Start
				* @see https://tailwindcss.com/docs/scroll-margin
				*/
				"scroll-mbs": [{ "scroll-mbs": scaleUnambiguousSpacing() }],
				/**
				* Scroll Margin Block End
				* @see https://tailwindcss.com/docs/scroll-margin
				*/
				"scroll-mbe": [{ "scroll-mbe": scaleUnambiguousSpacing() }],
				/**
				* Scroll Margin Top
				* @see https://tailwindcss.com/docs/scroll-margin
				*/
				"scroll-mt": [{ "scroll-mt": scaleUnambiguousSpacing() }],
				/**
				* Scroll Margin Right
				* @see https://tailwindcss.com/docs/scroll-margin
				*/
				"scroll-mr": [{ "scroll-mr": scaleUnambiguousSpacing() }],
				/**
				* Scroll Margin Bottom
				* @see https://tailwindcss.com/docs/scroll-margin
				*/
				"scroll-mb": [{ "scroll-mb": scaleUnambiguousSpacing() }],
				/**
				* Scroll Margin Left
				* @see https://tailwindcss.com/docs/scroll-margin
				*/
				"scroll-ml": [{ "scroll-ml": scaleUnambiguousSpacing() }],
				/**
				* Scroll Padding
				* @see https://tailwindcss.com/docs/scroll-padding
				*/
				"scroll-p": [{ "scroll-p": scaleUnambiguousSpacing() }],
				/**
				* Scroll Padding Inline
				* @see https://tailwindcss.com/docs/scroll-padding
				*/
				"scroll-px": [{ "scroll-px": scaleUnambiguousSpacing() }],
				/**
				* Scroll Padding Block
				* @see https://tailwindcss.com/docs/scroll-padding
				*/
				"scroll-py": [{ "scroll-py": scaleUnambiguousSpacing() }],
				/**
				* Scroll Padding Inline Start
				* @see https://tailwindcss.com/docs/scroll-padding
				*/
				"scroll-ps": [{ "scroll-ps": scaleUnambiguousSpacing() }],
				/**
				* Scroll Padding Inline End
				* @see https://tailwindcss.com/docs/scroll-padding
				*/
				"scroll-pe": [{ "scroll-pe": scaleUnambiguousSpacing() }],
				/**
				* Scroll Padding Block Start
				* @see https://tailwindcss.com/docs/scroll-padding
				*/
				"scroll-pbs": [{ "scroll-pbs": scaleUnambiguousSpacing() }],
				/**
				* Scroll Padding Block End
				* @see https://tailwindcss.com/docs/scroll-padding
				*/
				"scroll-pbe": [{ "scroll-pbe": scaleUnambiguousSpacing() }],
				/**
				* Scroll Padding Top
				* @see https://tailwindcss.com/docs/scroll-padding
				*/
				"scroll-pt": [{ "scroll-pt": scaleUnambiguousSpacing() }],
				/**
				* Scroll Padding Right
				* @see https://tailwindcss.com/docs/scroll-padding
				*/
				"scroll-pr": [{ "scroll-pr": scaleUnambiguousSpacing() }],
				/**
				* Scroll Padding Bottom
				* @see https://tailwindcss.com/docs/scroll-padding
				*/
				"scroll-pb": [{ "scroll-pb": scaleUnambiguousSpacing() }],
				/**
				* Scroll Padding Left
				* @see https://tailwindcss.com/docs/scroll-padding
				*/
				"scroll-pl": [{ "scroll-pl": scaleUnambiguousSpacing() }],
				/**
				* Scroll Snap Align
				* @see https://tailwindcss.com/docs/scroll-snap-align
				*/
				"snap-align": [{ snap: [
					"start",
					"end",
					"center",
					"align-none"
				] }],
				/**
				* Scroll Snap Stop
				* @see https://tailwindcss.com/docs/scroll-snap-stop
				*/
				"snap-stop": [{ snap: ["normal", "always"] }],
				/**
				* Scroll Snap Type
				* @see https://tailwindcss.com/docs/scroll-snap-type
				*/
				"snap-type": [{ snap: [
					"none",
					"x",
					"y",
					"both"
				] }],
				/**
				* Scroll Snap Type Strictness
				* @see https://tailwindcss.com/docs/scroll-snap-type
				*/
				"snap-strictness": [{ snap: ["mandatory", "proximity"] }],
				/**
				* Touch Action
				* @see https://tailwindcss.com/docs/touch-action
				*/
				touch: [{ touch: [
					"auto",
					"none",
					"manipulation"
				] }],
				/**
				* Touch Action X
				* @see https://tailwindcss.com/docs/touch-action
				*/
				"touch-x": [{ "touch-pan": [
					"x",
					"left",
					"right"
				] }],
				/**
				* Touch Action Y
				* @see https://tailwindcss.com/docs/touch-action
				*/
				"touch-y": [{ "touch-pan": [
					"y",
					"up",
					"down"
				] }],
				/**
				* Touch Action Pinch Zoom
				* @see https://tailwindcss.com/docs/touch-action
				*/
				"touch-pz": ["touch-pinch-zoom"],
				/**
				* User Select
				* @see https://tailwindcss.com/docs/user-select
				*/
				select: [{ select: [
					"none",
					"text",
					"all",
					"auto"
				] }],
				/**
				* Will Change
				* @see https://tailwindcss.com/docs/will-change
				*/
				"will-change": [{ "will-change": [
					"auto",
					"scroll",
					"contents",
					"transform",
					isArbitraryVariable,
					isArbitraryValue
				] }],
				/**
				* Fill
				* @see https://tailwindcss.com/docs/fill
				*/
				fill: [{ fill: ["none", ...scaleColor()] }],
				/**
				* Stroke Width
				* @see https://tailwindcss.com/docs/stroke-width
				*/
				"stroke-w": [{ stroke: [
					isNumber,
					isArbitraryVariableLength,
					isArbitraryLength,
					isArbitraryNumber
				] }],
				/**
				* Stroke
				* @see https://tailwindcss.com/docs/stroke
				*/
				stroke: [{ stroke: ["none", ...scaleColor()] }],
				/**
				* Forced Color Adjust
				* @see https://tailwindcss.com/docs/forced-color-adjust
				*/
				"forced-color-adjust": [{ "forced-color-adjust": ["auto", "none"] }]
			},
			conflictingClassGroups: {
				overflow: ["overflow-x", "overflow-y"],
				overscroll: ["overscroll-x", "overscroll-y"],
				inset: [
					"inset-x",
					"inset-y",
					"inset-bs",
					"inset-be",
					"start",
					"end",
					"top",
					"right",
					"bottom",
					"left"
				],
				"inset-x": ["right", "left"],
				"inset-y": ["top", "bottom"],
				flex: [
					"basis",
					"grow",
					"shrink"
				],
				gap: ["gap-x", "gap-y"],
				p: [
					"px",
					"py",
					"ps",
					"pe",
					"pbs",
					"pbe",
					"pt",
					"pr",
					"pb",
					"pl"
				],
				px: ["pr", "pl"],
				py: ["pt", "pb"],
				m: [
					"mx",
					"my",
					"ms",
					"me",
					"mbs",
					"mbe",
					"mt",
					"mr",
					"mb",
					"ml"
				],
				mx: ["mr", "ml"],
				my: ["mt", "mb"],
				size: ["w", "h"],
				"font-size": ["leading"],
				"fvn-normal": [
					"fvn-ordinal",
					"fvn-slashed-zero",
					"fvn-figure",
					"fvn-spacing",
					"fvn-fraction"
				],
				"fvn-ordinal": ["fvn-normal"],
				"fvn-slashed-zero": ["fvn-normal"],
				"fvn-figure": ["fvn-normal"],
				"fvn-spacing": ["fvn-normal"],
				"fvn-fraction": ["fvn-normal"],
				"line-clamp": ["display", "overflow"],
				rounded: [
					"rounded-s",
					"rounded-e",
					"rounded-t",
					"rounded-r",
					"rounded-b",
					"rounded-l",
					"rounded-ss",
					"rounded-se",
					"rounded-ee",
					"rounded-es",
					"rounded-tl",
					"rounded-tr",
					"rounded-br",
					"rounded-bl"
				],
				"rounded-s": ["rounded-ss", "rounded-es"],
				"rounded-e": ["rounded-se", "rounded-ee"],
				"rounded-t": ["rounded-tl", "rounded-tr"],
				"rounded-r": ["rounded-tr", "rounded-br"],
				"rounded-b": ["rounded-br", "rounded-bl"],
				"rounded-l": ["rounded-tl", "rounded-bl"],
				"border-spacing": ["border-spacing-x", "border-spacing-y"],
				"border-w": [
					"border-w-x",
					"border-w-y",
					"border-w-s",
					"border-w-e",
					"border-w-bs",
					"border-w-be",
					"border-w-t",
					"border-w-r",
					"border-w-b",
					"border-w-l"
				],
				"border-w-x": ["border-w-r", "border-w-l"],
				"border-w-y": ["border-w-t", "border-w-b"],
				"border-color": [
					"border-color-x",
					"border-color-y",
					"border-color-s",
					"border-color-e",
					"border-color-bs",
					"border-color-be",
					"border-color-t",
					"border-color-r",
					"border-color-b",
					"border-color-l"
				],
				"border-color-x": ["border-color-r", "border-color-l"],
				"border-color-y": ["border-color-t", "border-color-b"],
				translate: [
					"translate-x",
					"translate-y",
					"translate-none"
				],
				"translate-none": [
					"translate",
					"translate-x",
					"translate-y",
					"translate-z"
				],
				"scroll-m": [
					"scroll-mx",
					"scroll-my",
					"scroll-ms",
					"scroll-me",
					"scroll-mbs",
					"scroll-mbe",
					"scroll-mt",
					"scroll-mr",
					"scroll-mb",
					"scroll-ml"
				],
				"scroll-mx": ["scroll-mr", "scroll-ml"],
				"scroll-my": ["scroll-mt", "scroll-mb"],
				"scroll-p": [
					"scroll-px",
					"scroll-py",
					"scroll-ps",
					"scroll-pe",
					"scroll-pbs",
					"scroll-pbe",
					"scroll-pt",
					"scroll-pr",
					"scroll-pb",
					"scroll-pl"
				],
				"scroll-px": ["scroll-pr", "scroll-pl"],
				"scroll-py": ["scroll-pt", "scroll-pb"],
				touch: [
					"touch-x",
					"touch-y",
					"touch-pz"
				],
				"touch-x": ["touch"],
				"touch-y": ["touch"],
				"touch-pz": ["touch"]
			},
			conflictingClassGroupModifiers: { "font-size": ["leading"] },
			orderSensitiveModifiers: [
				"*",
				"**",
				"after",
				"backdrop",
				"before",
				"details-content",
				"file",
				"first-letter",
				"first-line",
				"marker",
				"placeholder",
				"selection"
			]
		};
	};
	var twMerge = /* @__PURE__ */ createTailwindMerge(getDefaultConfig);
	//#endregion
	//#region bot/app/web/frontend/src/lib/utils.js
	function cn(...inputs) {
		return twMerge(clsx$1(inputs));
	}
	//#endregion
	//#region bot/app/web/frontend/src/lib/components/ui/button.svelte
	var root_1$3 = /* @__PURE__ */ from_html(`<a><!></a>`);
	var root_2$2 = /* @__PURE__ */ from_html(`<button><!></button>`);
	function Button($$anchor, $$props) {
		const $$restProps = legacy_rest_props(legacy_rest_props($$props, [
			"children",
			"$$slots",
			"$$events",
			"$$legacy"
		]), [
			"type",
			"variant",
			"size",
			"disabled",
			"href",
			"onclick",
			"class"
		]);
		push($$props, false);
		let type = prop($$props, "type", 8, "button");
		let variant = prop($$props, "variant", 8, "default");
		let size = prop($$props, "size", 8, "default");
		let disabled = prop($$props, "disabled", 8, false);
		let href = prop($$props, "href", 8, "");
		let onclick = prop($$props, "onclick", 8, void 0);
		let className = prop($$props, "class", 8, "");
		const variants = {
			default: "btn btn-primary",
			secondary: "btn btn-secondary",
			outline: "btn btn-outline",
			ghost: "btn btn-ghost",
			telegram: "btn btn-telegram",
			icon: "btn btn-icon"
		};
		const sizes = {
			default: "",
			sm: "btn-sm",
			lg: "btn-lg",
			icon: "btn-square"
		};
		init();
		var fragment = comment();
		var node = first_child(fragment);
		var consequent = ($$anchor) => {
			var a = root_1$3();
			attribute_effect(a, ($0) => ({
				class: $0,
				href: href(),
				...$$restProps
			}), [() => (deep_read_state(cn), deep_read_state(variant()), deep_read_state(size()), deep_read_state(className()), untrack(() => cn(variants[variant()], sizes[size()], className())))]);
			slot(child(a), $$props, "default", {}, null);
			reset(a);
			event("click", a, function(...$$args) {
				onclick()?.apply(this, $$args);
			});
			append($$anchor, a);
		};
		var alternate = ($$anchor) => {
			var button = root_2$2();
			attribute_effect(button, ($0) => ({
				class: $0,
				type: type(),
				disabled: disabled(),
				...$$restProps
			}), [() => (deep_read_state(cn), deep_read_state(variant()), deep_read_state(size()), deep_read_state(className()), untrack(() => cn(variants[variant()], sizes[size()], className())))]);
			slot(child(button), $$props, "default", {}, null);
			reset(button);
			event("click", button, function(...$$args) {
				onclick()?.apply(this, $$args);
			});
			append($$anchor, button);
		};
		if_block(node, ($$render) => {
			if (href()) $$render(consequent);
			else $$render(alternate, -1);
		});
		append($$anchor, fragment);
		pop();
	}
	//#endregion
	//#region bot/app/web/frontend/src/lib/components/ui/card.svelte
	var root$6 = /* @__PURE__ */ from_html(`<section><!></section>`);
	function Card($$anchor, $$props) {
		push($$props, false);
		let active = prop($$props, "active", 8, false);
		let compact = prop($$props, "compact", 8, false);
		let className = prop($$props, "class", 8, "");
		init();
		var section = root$6();
		slot(child(section), $$props, "default", {}, null);
		reset(section);
		template_effect(($0) => set_class(section, 1, $0), [() => clsx((deep_read_state(cn), deep_read_state(active()), deep_read_state(compact()), deep_read_state(className()), untrack(() => cn("card", active() && "card-active", compact() && "card-compact", className()))))]);
		append($$anchor, section);
		pop();
	}
	//#endregion
	//#region bot/app/web/frontend/src/lib/components/ui/dialog.svelte
	var root_2$1 = /* @__PURE__ */ from_html(`<h2> </h2>`);
	var root_3$2 = /* @__PURE__ */ from_html(`<p> </p>`);
	var root_1$2 = /* @__PURE__ */ from_html(`<div class="dialog" role="dialog" aria-modal="true"><button class="dialog-backdrop" type="button" aria-label="Закрыть"></button> <section><div class="dialog-head"><div><!> <!></div> <!></div> <!></section></div>`);
	function Dialog($$anchor, $$props) {
		push($$props, false);
		let open = prop($$props, "open", 8, false);
		let title = prop($$props, "title", 8, "");
		let description = prop($$props, "description", 8, "");
		let onclose = prop($$props, "onclose", 8, () => {});
		let className = prop($$props, "class", 8, "");
		init();
		var fragment = comment();
		var node = first_child(fragment);
		var consequent_2 = ($$anchor) => {
			var div = root_1$2();
			var button = child(div);
			var section = sibling(button, 2);
			var div_1 = child(section);
			var div_2 = child(div_1);
			var node_1 = child(div_2);
			var consequent = ($$anchor) => {
				var h2 = root_2$1();
				var text = child(h2, true);
				reset(h2);
				template_effect(() => set_text(text, title()));
				append($$anchor, h2);
			};
			if_block(node_1, ($$render) => {
				if (title()) $$render(consequent);
			});
			var node_2 = sibling(node_1, 2);
			var consequent_1 = ($$anchor) => {
				var p = root_3$2();
				var text_1 = child(p, true);
				reset(p);
				template_effect(() => set_text(text_1, description()));
				append($$anchor, p);
			};
			if_block(node_2, ($$render) => {
				if (description()) $$render(consequent_1);
			});
			reset(div_2);
			Button(sibling(div_2, 2), {
				variant: "icon",
				size: "icon",
				get onclick() {
					return onclose();
				},
				"aria-label": "Закрыть",
				children: ($$anchor, $$slotProps) => {
					X($$anchor, { size: 18 });
				},
				$$slots: { default: true }
			});
			reset(div_1);
			slot(sibling(div_1, 2), $$props, "default", {}, null);
			reset(section);
			reset(div);
			template_effect(($0) => {
				set_attribute(div, "aria-label", title());
				set_class(section, 1, $0);
			}, [() => clsx((deep_read_state(cn), deep_read_state(className()), untrack(() => cn("dialog-card", className()))))]);
			event("click", button, function(...$$args) {
				onclose()?.apply(this, $$args);
			});
			append($$anchor, div);
		};
		if_block(node, ($$render) => {
			if (open()) $$render(consequent_2);
		});
		append($$anchor, fragment);
		pop();
	}
	//#endregion
	//#region bot/app/web/frontend/src/lib/components/ui/input.svelte
	var root$5 = /* @__PURE__ */ from_html(`<input/>`);
	function Input($$anchor, $$props) {
		push($$props, false);
		let value = prop($$props, "value", 12, "");
		let type = prop($$props, "type", 8, "text");
		let placeholder = prop($$props, "placeholder", 8, "");
		let inputmode = prop($$props, "inputmode", 8, void 0);
		let maxlength = prop($$props, "maxlength", 8, void 0);
		let autocomplete = prop($$props, "autocomplete", 8, void 0);
		let disabled = prop($$props, "disabled", 8, false);
		let className = prop($$props, "class", 8, "");
		init();
		var input = root$5();
		remove_input_defaults(input);
		template_effect(($0) => {
			set_class(input, 1, $0);
			set_attribute(input, "type", type());
			set_attribute(input, "placeholder", placeholder());
			set_attribute(input, "inputmode", inputmode());
			set_attribute(input, "maxlength", maxlength());
			set_attribute(input, "autocomplete", autocomplete());
			input.disabled = disabled();
		}, [() => clsx((deep_read_state(cn), deep_read_state(className()), untrack(() => cn("input", className()))))]);
		bind_value(input, value);
		append($$anchor, input);
		pop();
	}
	//#endregion
	//#region bot/app/web/frontend/src/preview/BackTitle.svelte
	var root$4 = /* @__PURE__ */ from_html(`<header class="screen-head"><button class="btn btn-icon btn-square" type="button" aria-label="Назад"><!></button> <div class="center-copy"><h1> </h1> <p> </p></div> <span></span></header>`);
	function BackTitle($$anchor, $$props) {
		let title = prop($$props, "title", 8, "");
		let subtitle = prop($$props, "subtitle", 8, "");
		var header = root$4();
		var button = child(header);
		Arrow_left(child(button), { size: 18 });
		reset(button);
		var div = sibling(button, 2);
		var h1 = child(div);
		var text = child(h1, true);
		reset(h1);
		var p = sibling(h1, 2);
		var text_1 = child(p, true);
		reset(p);
		reset(div);
		next(2);
		reset(header);
		template_effect(() => {
			set_text(text, title());
			set_text(text_1, subtitle());
		});
		append($$anchor, header);
	}
	//#endregion
	//#region bot/app/web/frontend/src/preview/PhoneFrame.svelte
	var root$3 = /* @__PURE__ */ from_html(`<section><h2><span> </span> </h2> <div class="preview-phone"><!></div></section>`);
	function PhoneFrame($$anchor, $$props) {
		let number = prop($$props, "number", 8, "");
		let label = prop($$props, "label", 8, "");
		let wide = prop($$props, "wide", 8, false);
		var section = root$3();
		let classes;
		var h2 = child(section);
		var span = child(h2);
		var text = child(span);
		reset(span);
		var text_1 = sibling(span);
		reset(h2);
		var div = sibling(h2, 2);
		slot(child(div), $$props, "default", {}, null);
		reset(div);
		reset(section);
		template_effect(() => {
			classes = set_class(section, 1, "preview-phone-wrap", null, classes, { wide: wide() });
			set_text(text, `${number() ?? ""}.`);
			set_text(text_1, ` ${label() ?? ""}`);
		});
		append($$anchor, section);
	}
	//#endregion
	//#region bot/app/web/frontend/src/preview/PreviewMethods.svelte
	var root_1$1 = /* @__PURE__ */ from_html(`<div><!> <span><strong> </strong> <small> </small></span></div>`);
	var root$2 = /* @__PURE__ */ from_html(`<div class="method-grid"></div>`);
	function PreviewMethods($$anchor, $$props) {
		let methods = prop($$props, "methods", 24, () => []);
		const icons = [
			Credit_card,
			Send,
			Wallet_cards,
			Wallet_cards
		];
		function note(index) {
			if (index === 0) return "Visa, Mastercard";
			if (index === 1) return "Быстро и удобно";
			if (index === 2) return "USDT, BTC, ETH";
			return "ЮMoney, СБП и др.";
		}
		var div = root$2();
		each(div, 5, methods, index, ($$anchor, method, index) => {
			var div_1 = root_1$1();
			set_class(div_1, 1, "method-card", null, {}, { active: index === 1 });
			var node = child(div_1);
			component(node, () => icons[index] || Wallet_cards, ($$anchor, $$component) => {
				$$component($$anchor, { size: 18 });
			});
			var span = sibling(node, 2);
			var strong = child(span);
			var text = child(strong, true);
			reset(strong);
			var small = sibling(strong, 2);
			var text_1 = child(small, true);
			reset(small);
			reset(span);
			reset(div_1);
			template_effect(($0) => {
				set_text(text, (get(method), untrack(() => get(method).name)));
				set_text(text_1, $0);
			}, [() => untrack(() => note(index))]);
			append($$anchor, div_1);
		});
		reset(div);
		append($$anchor, div);
	}
	//#endregion
	//#region bot/app/web/frontend/src/preview/PreviewNav.svelte
	var root$1 = /* @__PURE__ */ from_html(`<nav class="bottom-nav static"><button type="button"><!><span>Главная</span></button> <button type="button"><!><span>Пригласить</span></button> <button type="button"><!><span>Настройки</span></button></nav>`);
	function PreviewNav($$anchor, $$props) {
		let active = prop($$props, "active", 8, "home");
		var nav = root$1();
		var button = child(nav);
		let classes;
		House(child(button), { size: 20 });
		next();
		reset(button);
		var button_1 = sibling(button, 2);
		let classes_1;
		Gift(child(button_1), { size: 20 });
		next();
		reset(button_1);
		var button_2 = sibling(button_1, 2);
		let classes_2;
		Settings(child(button_2), { size: 20 });
		next();
		reset(button_2);
		reset(nav);
		template_effect(() => {
			classes = set_class(button, 1, "", null, classes, { active: active() === "home" });
			classes_1 = set_class(button_1, 1, "", null, classes_1, { active: active() === "invite" });
			classes_2 = set_class(button_2, 1, "", null, classes_2, { active: active() === "settings" });
		});
		append($$anchor, nav);
	}
	//#endregion
	//#region bot/app/web/frontend/src/PreviewBoard.svelte
	var root_2 = /* @__PURE__ */ from_html(`<div class="sub-status"><!> <div><h2>Подписка активна</h2><p> </p></div></div>`);
	var root_3$1 = /* @__PURE__ */ from_html(`<div class="traffic-top"><span>Использовано трафика</span><strong> </strong></div> <div class="progress"><span style="width: 18%"></span></div> <div class="traffic-percent">18%</div>`, 1);
	var root_4$1 = /* @__PURE__ */ from_html(`<!>Установить и настроить`, 1);
	var root_5$1 = /* @__PURE__ */ from_html(`<!>Продлить`, 1);
	var root_6$1 = /* @__PURE__ */ from_html(`<!>Сменить тариф`, 1);
	var root_1 = /* @__PURE__ */ from_html(`<main class="home-layout"><div class="login-brand home-brand"><div class="brand-mark brand-mark-xl"><span> </span></div> <h1> </h1></div> <div class="home-bottom"><!> <!> <div class="action-stack"><!> <!> <!></div></div> <!></main>`);
	var root_8$1 = /* @__PURE__ */ from_html(`<div><span class="select-icon"><!></span> <span><strong> </strong><small> </small><em> </em></span> <!></div>`);
	var root_11 = /* @__PURE__ */ from_html(`Далее <!>`, 1);
	var root_7$1 = /* @__PURE__ */ from_html(`<div class="preview-header"><div class="brand-row"><div class="brand-mark"><span> </span></div><strong> </strong></div></div> <div class="tariff-list"></div> <!>`, 1);
	var root_13$1 = /* @__PURE__ */ from_html(`<div><strong> </strong><span> </span><small> </small> <!></div>`);
	var root_15$1 = /* @__PURE__ */ from_html(`<span>Итого<br/><small>К оплате</small></span><strong>790 ₽</strong>`, 1);
	var root_16$1 = /* @__PURE__ */ from_html(`Оплатить 790 ₽ <!>`, 1);
	var root_12$1 = /* @__PURE__ */ from_html(`<!> <div class="period-grid"></div> <!> <!> <!>`, 1);
	var root_18$1 = /* @__PURE__ */ from_html(`<div><strong> </strong><span> </span><small> </small> <!></div>`);
	var root_20 = /* @__PURE__ */ from_html(`<span>Итого<br/><small>К оплате</small></span><strong>990 ₽</strong>`, 1);
	var root_21$1 = /* @__PURE__ */ from_html(`Оплатить 990 ₽ <!>`, 1);
	var root_17$1 = /* @__PURE__ */ from_html(`<!> <div class="period-grid"></div> <!> <!> <!>`, 1);
	var root_23$1 = /* @__PURE__ */ from_html(`Далее <!>`, 1);
	var root_22$1 = /* @__PURE__ */ from_html(`<!> <div class="tariff-list compact"><div class="select-card"><span><strong>Подписка</strong><small>Безлимитный трафик</small></span><em>Доплата 190 ₽</em><!></div> <div class="select-card active"><span><strong>Трафик</strong><small>Пакеты гигабайт</small></span><em>Доплата не требуется</em><!></div> <div class="select-card"><span><strong>Премиум</strong><small>Максимальная скорость</small></span><em>Доплата 390 ₽</em><!></div></div> <!> <div class="preview-modal"><!> <strong>Сменить тариф без доплаты?</strong> <p>Остаток 12 дней будет пересчитан по новому тарифу.</p> <!> <!></div>`, 1);
	var root_28$1 = /* @__PURE__ */ from_html(`Копировать <!>`, 1);
	var root_27$1 = /* @__PURE__ */ from_html(`<div class="card-label">Ваша реферальная ссылка</div> <div class="copy-row"><code>https://minishop.app/ref/ABCD1234</code><!></div>`, 1);
	var root_29$1 = /* @__PURE__ */ from_html(`<!><div><span>Ваш бонус</span><strong>+7 дней за каждого друга</strong><p>Друг получит +3 дня к подписке.</p></div>`, 1);
	var root_30$1 = /* @__PURE__ */ from_html(`<!>Активировать промокод`, 1);
	var root_26$1 = /* @__PURE__ */ from_html(`<div class="preview-header"><div class="brand-row"><div class="brand-mark"><span> </span></div><strong> </strong></div></div> <!> <!> <!>`, 1);
	var root_33$1 = /* @__PURE__ */ from_html(`<img alt="Аватар пользователя"/>`);
	var root_32$1 = /* @__PURE__ */ from_html(`<div class="settings-avatar"><!></div> <div class="settings-profile-meta"><strong> </strong> <small> </small> <small> </small></div>`, 1);
	var root_35$1 = /* @__PURE__ */ from_html(`<div class="settings-row"><!> <span><strong> </strong><small> </small></span> <!></div>`);
	var root_31$1 = /* @__PURE__ */ from_html(`<div class="preview-header"><div class="brand-row"><div class="brand-mark"><span> </span></div><strong> </strong></div></div> <!> <div class="settings-list"></div>`, 1);
	var root_38$1 = /* @__PURE__ */ from_html(`<!>Получить код`, 1);
	var root_39 = /* @__PURE__ */ from_html(`<!>Войти через Telegram`, 1);
	var root_37 = /* @__PURE__ */ from_html(`<div class="field-label">Вход по email</div> <div class="email-row"><div class="input muted">Email</div><!></div> <div class="or-line"><span></span>или<span></span></div> <!>`, 1);
	var root_36$1 = /* @__PURE__ */ from_html(`<div class="login-brand small"><div class="brand-mark brand-mark-xl"><span> </span></div> <h1> </h1><p>Войдите в свой аккаунт</p></div> <!> <div class="auth-bottom">Нет аккаунта? <strong>Создать</strong></div>`, 1);
	var root_41$1 = /* @__PURE__ */ from_html(`<span> </span>`);
	var root_40 = /* @__PURE__ */ from_html(`<!> <div class="otp-slots static"></div> <!> <button class="link-button"><!>Отправить код повторно (00:45)</button>`, 1);
	var root = /* @__PURE__ */ from_html(`<div class="preview-board"><!> <!> <!> <!> <!> <!> <!> <!> <!></div>`);
	function PreviewBoard($$anchor, $$props) {
		push($$props, false);
		let config = prop($$props, "config", 24, () => ({}));
		let mockData = prop($$props, "mockData", 24, () => ({}));
		const title = config().title || "/minishop";
		const logoEmoji = config().logoEmoji || "🫥";
		const plans = mockData().plans || [];
		const sub = mockData().subscription || {};
		const methods = mockData().payment_methods || [];
		const user = mockData().user || {};
		const tariffs = [
			[
				"subscription",
				"Подписка",
				"Безлимитный трафик",
				"Идеально для постоянного использования",
				Zap
			],
			[
				"traffic",
				"Трафик",
				"Пакеты гигабайт",
				"Платите только за нужный объем",
				Database
			],
			[
				"premium",
				"Премиум",
				"Максимальная скорость",
				"Приоритетные серверы и поддержка",
				Crown
			]
		];
		const traffic = [
			[20, 290],
			[50, 590],
			[100, 990],
			[300, 2190]
		];
		const settingsRows = [
			[
				Earth,
				"Язык интерфейса",
				"Русский"
			],
			[
				Send,
				"Привязка Telegram",
				user.telegram_linked ? `@${user.username || "username"}` : "Не привязан"
			],
			[
				Mail,
				"Привязка почты",
				user.email || "Не привязана"
			],
			[
				User_round,
				"Выйти",
				"Завершить сессию"
			]
		];
		const previewTelegramName = user.first_name || (user.username ? `@${user.username}` : "Telegram не привязан");
		const previewEmail = user.email || "Почта не привязана";
		const previewTelegramId = user.telegram_id ? `TG ID ${user.telegram_id}` : "TG ID не привязан";
		const previewAvatar = user.telegram_photo_url || "";
		function money(value) {
			return `${value} ₽`;
		}
		init();
		var div = root();
		var node = child(div);
		PhoneFrame(node, {
			number: "1",
			label: "Главный экран",
			children: ($$anchor, $$slotProps) => {
				var main = root_1();
				var div_1 = child(main);
				var div_2 = child(div_1);
				var span = child(div_2);
				var text = child(span, true);
				reset(span);
				reset(div_2);
				var h1 = sibling(div_2, 2);
				var text_1 = child(h1, true);
				reset(h1);
				reset(div_1);
				var div_3 = sibling(div_1, 2);
				var node_1 = child(div_3);
				Card(node_1, {
					class: "status-card",
					children: ($$anchor, $$slotProps) => {
						var div_4 = root_2();
						var node_2 = child(div_4);
						Circle_check(node_2, { size: 23 });
						var div_5 = sibling(node_2, 2);
						var p = sibling(child(div_5));
						var text_2 = child(p);
						reset(p);
						reset(div_5);
						reset(div_4);
						template_effect(() => set_text(text_2, `до ${untrack(() => sub.end_date_text) ?? ""}`));
						append($$anchor, div_4);
					},
					$$slots: { default: true }
				});
				var node_3 = sibling(node_1, 2);
				Card(node_3, {
					children: ($$anchor, $$slotProps) => {
						var fragment = root_3$1();
						var div_6 = first_child(fragment);
						var strong = sibling(child(div_6));
						var text_3 = child(strong);
						reset(strong);
						reset(div_6);
						next(4);
						template_effect(() => set_text(text_3, `${untrack(() => sub.traffic_used) ?? ""} из ${untrack(() => sub.traffic_limit) ?? ""}`));
						append($$anchor, fragment);
					},
					$$slots: { default: true }
				});
				var div_7 = sibling(node_3, 2);
				var node_4 = child(div_7);
				Button(node_4, {
					class: "wide",
					children: ($$anchor, $$slotProps) => {
						var fragment_1 = root_4$1();
						Download(first_child(fragment_1), { size: 17 });
						next();
						append($$anchor, fragment_1);
					},
					$$slots: { default: true }
				});
				var node_6 = sibling(node_4, 2);
				Button(node_6, {
					variant: "secondary",
					class: "wide",
					children: ($$anchor, $$slotProps) => {
						var fragment_2 = root_5$1();
						Refresh_cw(first_child(fragment_2), { size: 17 });
						next();
						append($$anchor, fragment_2);
					},
					$$slots: { default: true }
				});
				Button(sibling(node_6, 2), {
					variant: "secondary",
					class: "wide",
					children: ($$anchor, $$slotProps) => {
						var fragment_3 = root_6$1();
						Repeat_2(first_child(fragment_3), { size: 17 });
						next();
						append($$anchor, fragment_3);
					},
					$$slots: { default: true }
				});
				reset(div_7);
				reset(div_3);
				PreviewNav(sibling(div_3, 2), { active: "home" });
				reset(main);
				template_effect(() => {
					set_text(text, logoEmoji);
					set_text(text_1, title);
				});
				append($$anchor, main);
			},
			$$slots: { default: true }
		});
		var node_11 = sibling(node, 2);
		PhoneFrame(node_11, {
			number: "2",
			label: "Выбор тарифа",
			children: ($$anchor, $$slotProps) => {
				var fragment_4 = root_7$1();
				var div_8 = first_child(fragment_4);
				var div_9 = child(div_8);
				var div_10 = child(div_9);
				var span_1 = child(div_10);
				var text_4 = child(span_1, true);
				reset(span_1);
				reset(div_10);
				var strong_1 = sibling(div_10);
				var text_5 = child(strong_1, true);
				reset(strong_1);
				reset(div_9);
				reset(div_8);
				var div_11 = sibling(div_8, 2);
				each(div_11, 5, () => tariffs, index, ($$anchor, tariff, index) => {
					var div_12 = root_8$1();
					set_class(div_12, 1, "select-card", null, {}, { active: index === 0 });
					var span_2 = child(div_12);
					component(child(span_2), () => get(tariff)[4], ($$anchor, $$component) => {
						$$component($$anchor, { size: 24 });
					});
					reset(span_2);
					var span_3 = sibling(span_2, 2);
					var strong_2 = child(span_3);
					var text_6 = child(strong_2, true);
					reset(strong_2);
					var small = sibling(strong_2);
					var text_7 = child(small, true);
					reset(small);
					var em = sibling(small);
					var text_8 = child(em, true);
					reset(em);
					reset(span_3);
					var node_13 = sibling(span_3, 2);
					var consequent = ($$anchor) => {
						Circle_check($$anchor, { size: 21 });
					};
					var alternate = ($$anchor) => {
						Circle($$anchor, { size: 21 });
					};
					if_block(node_13, ($$render) => {
						if (index === 0) $$render(consequent);
						else $$render(alternate, -1);
					});
					reset(div_12);
					template_effect(() => {
						set_text(text_6, (get(tariff), untrack(() => get(tariff)[1])));
						set_text(text_7, (get(tariff), untrack(() => get(tariff)[2])));
						set_text(text_8, (get(tariff), untrack(() => get(tariff)[3])));
					});
					append($$anchor, div_12);
				});
				reset(div_11);
				Button(sibling(div_11, 2), {
					class: "wide bottom-action",
					children: ($$anchor, $$slotProps) => {
						next();
						var fragment_7 = root_11();
						Arrow_right(sibling(first_child(fragment_7)), { size: 17 });
						append($$anchor, fragment_7);
					},
					$$slots: { default: true }
				});
				template_effect(() => {
					set_text(text_4, logoEmoji);
					set_text(text_5, title);
				});
				append($$anchor, fragment_4);
			},
			$$slots: { default: true }
		});
		var node_16 = sibling(node_11, 2);
		PhoneFrame(node_16, {
			number: "3",
			label: "Оплата тарифа — подписка",
			wide: true,
			children: ($$anchor, $$slotProps) => {
				var fragment_8 = root_12$1();
				var node_17 = first_child(fragment_8);
				BackTitle(node_17, {
					title: "Подписка",
					subtitle: "Выберите срок подписки"
				});
				var div_13 = sibling(node_17, 2);
				each(div_13, 5, () => plans, index, ($$anchor, plan, index) => {
					var div_14 = root_13$1();
					set_class(div_14, 1, "period-card", null, {}, { active: index === 1 });
					var strong_3 = child(div_14);
					var text_9 = child(strong_3, true);
					reset(strong_3);
					var span_4 = sibling(strong_3);
					var text_10 = child(span_4, true);
					reset(span_4);
					var small_1 = sibling(span_4);
					var text_11 = child(small_1);
					reset(small_1);
					var node_18 = sibling(small_1, 2);
					var consequent_1 = ($$anchor) => {
						Circle_check($$anchor, { size: 18 });
					};
					if_block(node_18, ($$render) => {
						if (index === 1) $$render(consequent_1);
					});
					reset(div_14);
					template_effect(($0, $1) => {
						set_text(text_9, (get(plan), untrack(() => get(plan).title)));
						set_text(text_10, $0);
						set_text(text_11, `${$1 ?? ""}/мес`);
					}, [() => (get(plan), untrack(() => money(get(plan).price))), () => (get(plan), untrack(() => money(Math.round(get(plan).price / get(plan).months))))]);
					append($$anchor, div_14);
				});
				reset(div_13);
				var node_19 = sibling(div_13, 2);
				Card(node_19, {
					class: "total-card",
					children: ($$anchor, $$slotProps) => {
						var fragment_10 = root_15$1();
						next();
						append($$anchor, fragment_10);
					},
					$$slots: { default: true }
				});
				var node_20 = sibling(node_19, 2);
				PreviewMethods(node_20, { get methods() {
					return methods;
				} });
				Button(sibling(node_20, 2), {
					class: "wide bottom-action",
					children: ($$anchor, $$slotProps) => {
						next();
						var fragment_11 = root_16$1();
						Lock_keyhole(sibling(first_child(fragment_11)), { size: 16 });
						append($$anchor, fragment_11);
					},
					$$slots: { default: true }
				});
				append($$anchor, fragment_8);
			},
			$$slots: { default: true }
		});
		var node_23 = sibling(node_16, 2);
		PhoneFrame(node_23, {
			number: "4",
			label: "Оплата тарифа — трафик",
			wide: true,
			children: ($$anchor, $$slotProps) => {
				var fragment_12 = root_17$1();
				var node_24 = first_child(fragment_12);
				BackTitle(node_24, {
					title: "Трафик",
					subtitle: "Выберите пакет трафика"
				});
				var div_15 = sibling(node_24, 2);
				each(div_15, 5, () => traffic, index, ($$anchor, pack, index) => {
					var div_16 = root_18$1();
					set_class(div_16, 1, "period-card", null, {}, { active: index === 2 });
					var strong_4 = child(div_16);
					var text_12 = child(strong_4);
					reset(strong_4);
					var span_5 = sibling(strong_4);
					var text_13 = child(span_5, true);
					reset(span_5);
					var small_2 = sibling(span_5);
					var text_14 = child(small_2);
					reset(small_2);
					var node_25 = sibling(small_2, 2);
					var consequent_2 = ($$anchor) => {
						Circle_check($$anchor, { size: 18 });
					};
					if_block(node_25, ($$render) => {
						if (index === 2) $$render(consequent_2);
					});
					reset(div_16);
					template_effect(($0, $1) => {
						set_text(text_12, `${(get(pack), untrack(() => get(pack)[0])) ?? ""} ГБ`);
						set_text(text_13, $0);
						set_text(text_14, `${$1 ?? ""}/ГБ`);
					}, [() => (get(pack), untrack(() => money(get(pack)[1]))), () => (get(pack), untrack(() => money(Math.round(get(pack)[1] / get(pack)[0]))))]);
					append($$anchor, div_16);
				});
				reset(div_15);
				var node_26 = sibling(div_15, 2);
				Card(node_26, {
					class: "total-card",
					children: ($$anchor, $$slotProps) => {
						var fragment_14 = root_20();
						next();
						append($$anchor, fragment_14);
					},
					$$slots: { default: true }
				});
				var node_27 = sibling(node_26, 2);
				PreviewMethods(node_27, { get methods() {
					return methods;
				} });
				Button(sibling(node_27, 2), {
					class: "wide bottom-action",
					children: ($$anchor, $$slotProps) => {
						next();
						var fragment_15 = root_21$1();
						Lock_keyhole(sibling(first_child(fragment_15)), { size: 16 });
						append($$anchor, fragment_15);
					},
					$$slots: { default: true }
				});
				append($$anchor, fragment_12);
			},
			$$slots: { default: true }
		});
		var node_30 = sibling(node_23, 2);
		PhoneFrame(node_30, {
			number: "5",
			label: "Смена тарифа",
			children: ($$anchor, $$slotProps) => {
				var fragment_16 = root_22$1();
				var node_31 = first_child(fragment_16);
				BackTitle(node_31, {
					title: "Смена тарифа",
					subtitle: "Остаток 12 дней будет пересчитан"
				});
				var div_17 = sibling(node_31, 2);
				var div_18 = child(div_17);
				Circle(sibling(child(div_18), 2), { size: 20 });
				reset(div_18);
				var div_19 = sibling(div_18, 2);
				Circle_check(sibling(child(div_19), 2), { size: 20 });
				reset(div_19);
				var div_20 = sibling(div_19, 2);
				Circle(sibling(child(div_20), 2), { size: 20 });
				reset(div_20);
				reset(div_17);
				var node_35 = sibling(div_17, 2);
				Button(node_35, {
					class: "wide bottom-action",
					children: ($$anchor, $$slotProps) => {
						next();
						var fragment_17 = root_23$1();
						Arrow_right(sibling(first_child(fragment_17)), { size: 17 });
						append($$anchor, fragment_17);
					},
					$$slots: { default: true }
				});
				var div_21 = sibling(node_35, 2);
				var node_37 = child(div_21);
				Repeat_2(node_37, { size: 30 });
				var node_38 = sibling(node_37, 6);
				Button(node_38, {
					children: ($$anchor, $$slotProps) => {
						next();
						append($$anchor, text("Да, сменить"));
					},
					$$slots: { default: true }
				});
				Button(sibling(node_38, 2), {
					variant: "secondary",
					children: ($$anchor, $$slotProps) => {
						next();
						append($$anchor, text("Отмена"));
					},
					$$slots: { default: true }
				});
				reset(div_21);
				append($$anchor, fragment_16);
			},
			$$slots: { default: true }
		});
		var node_40 = sibling(node_30, 2);
		PhoneFrame(node_40, {
			number: "6",
			label: "Пригласить друга",
			children: ($$anchor, $$slotProps) => {
				var fragment_18 = root_26$1();
				var div_22 = first_child(fragment_18);
				var div_23 = child(div_22);
				var div_24 = child(div_23);
				var span_6 = child(div_24);
				var text_17 = child(span_6, true);
				reset(span_6);
				reset(div_24);
				var strong_5 = sibling(div_24);
				var text_18 = child(strong_5, true);
				reset(strong_5);
				reset(div_23);
				reset(div_22);
				var node_41 = sibling(div_22, 2);
				Card(node_41, {
					children: ($$anchor, $$slotProps) => {
						var fragment_19 = root_27$1();
						var div_25 = sibling(first_child(fragment_19), 2);
						Button(sibling(child(div_25)), {
							children: ($$anchor, $$slotProps) => {
								next();
								var fragment_20 = root_28$1();
								Copy(sibling(first_child(fragment_20)), { size: 16 });
								append($$anchor, fragment_20);
							},
							$$slots: { default: true }
						});
						reset(div_25);
						append($$anchor, fragment_19);
					},
					$$slots: { default: true }
				});
				var node_44 = sibling(node_41, 2);
				Card(node_44, {
					class: "bonus-card",
					children: ($$anchor, $$slotProps) => {
						var fragment_21 = root_29$1();
						Gift(first_child(fragment_21), { size: 42 });
						next();
						append($$anchor, fragment_21);
					},
					$$slots: { default: true }
				});
				Button(sibling(node_44, 2), {
					variant: "outline",
					class: "wide",
					children: ($$anchor, $$slotProps) => {
						var fragment_22 = root_30$1();
						Ticket(first_child(fragment_22), { size: 18 });
						next();
						append($$anchor, fragment_22);
					},
					$$slots: { default: true }
				});
				template_effect(() => {
					set_text(text_17, logoEmoji);
					set_text(text_18, title);
				});
				append($$anchor, fragment_18);
			},
			$$slots: { default: true }
		});
		var node_48 = sibling(node_40, 2);
		PhoneFrame(node_48, {
			number: "7",
			label: "Настройки",
			children: ($$anchor, $$slotProps) => {
				var fragment_23 = root_31$1();
				var div_26 = first_child(fragment_23);
				var div_27 = child(div_26);
				var div_28 = child(div_27);
				var span_7 = child(div_28);
				var text_19 = child(span_7, true);
				reset(span_7);
				reset(div_28);
				var strong_6 = sibling(div_28);
				var text_20 = child(strong_6, true);
				reset(strong_6);
				reset(div_27);
				reset(div_26);
				var node_49 = sibling(div_26, 2);
				Card(node_49, {
					class: "settings-profile",
					children: ($$anchor, $$slotProps) => {
						var fragment_24 = root_32$1();
						var div_29 = first_child(fragment_24);
						var node_50 = child(div_29);
						var consequent_3 = ($$anchor) => {
							var img = root_33$1();
							template_effect(() => set_attribute(img, "src", previewAvatar));
							append($$anchor, img);
						};
						var alternate_1 = ($$anchor) => {
							User_round($$anchor, { size: 27 });
						};
						if_block(node_50, ($$render) => {
							if (previewAvatar) $$render(consequent_3);
							else $$render(alternate_1, -1);
						});
						reset(div_29);
						var div_30 = sibling(div_29, 2);
						var strong_7 = child(div_30);
						var text_21 = child(strong_7, true);
						reset(strong_7);
						var small_3 = sibling(strong_7, 2);
						var text_22 = child(small_3, true);
						reset(small_3);
						var small_4 = sibling(small_3, 2);
						var text_23 = child(small_4, true);
						reset(small_4);
						reset(div_30);
						template_effect(() => {
							set_text(text_21, previewTelegramName);
							set_text(text_22, previewEmail);
							set_text(text_23, previewTelegramId);
						});
						append($$anchor, fragment_24);
					},
					$$slots: { default: true }
				});
				var div_31 = sibling(node_49, 2);
				each(div_31, 5, () => settingsRows, index, ($$anchor, row) => {
					var div_32 = root_35$1();
					var node_51 = child(div_32);
					component(node_51, () => get(row)[0], ($$anchor, $$component) => {
						$$component($$anchor, { size: 20 });
					});
					var span_8 = sibling(node_51, 2);
					var strong_8 = child(span_8);
					var text_24 = child(strong_8, true);
					reset(strong_8);
					var small_5 = sibling(strong_8);
					var text_25 = child(small_5, true);
					reset(small_5);
					reset(span_8);
					Arrow_right(sibling(span_8, 2), { size: 16 });
					reset(div_32);
					template_effect(() => {
						set_text(text_24, (get(row), untrack(() => get(row)[1])));
						set_text(text_25, (get(row), untrack(() => get(row)[2])));
					});
					append($$anchor, div_32);
				});
				reset(div_31);
				template_effect(() => {
					set_text(text_19, logoEmoji);
					set_text(text_20, title);
				});
				append($$anchor, fragment_23);
			},
			$$slots: { default: true }
		});
		var node_53 = sibling(node_48, 2);
		PhoneFrame(node_53, {
			number: "8",
			label: "Логин",
			wide: true,
			children: ($$anchor, $$slotProps) => {
				var fragment_26 = root_36$1();
				var div_33 = first_child(fragment_26);
				var div_34 = child(div_33);
				var span_9 = child(div_34);
				var text_26 = child(span_9, true);
				reset(span_9);
				reset(div_34);
				var h1_1 = sibling(div_34, 2);
				var text_27 = child(h1_1, true);
				reset(h1_1);
				next();
				reset(div_33);
				Card(sibling(div_33, 2), {
					class: "auth-card",
					children: ($$anchor, $$slotProps) => {
						var fragment_27 = root_37();
						var div_35 = sibling(first_child(fragment_27), 2);
						Button(sibling(child(div_35)), {
							variant: "outline",
							children: ($$anchor, $$slotProps) => {
								var fragment_28 = root_38$1();
								Mail(first_child(fragment_28), { size: 17 });
								next();
								append($$anchor, fragment_28);
							},
							$$slots: { default: true }
						});
						reset(div_35);
						Button(sibling(div_35, 4), {
							variant: "telegram",
							class: "wide",
							children: ($$anchor, $$slotProps) => {
								var fragment_29 = root_39();
								Send(first_child(fragment_29), { size: 18 });
								next();
								append($$anchor, fragment_29);
							},
							$$slots: { default: true }
						});
						append($$anchor, fragment_27);
					},
					$$slots: { default: true }
				});
				next(2);
				template_effect(() => {
					set_text(text_26, logoEmoji);
					set_text(text_27, title);
				});
				append($$anchor, fragment_26);
			},
			$$slots: { default: true }
		});
		PhoneFrame(sibling(node_53, 2), {
			number: "9",
			label: "Подтверждение по коду",
			wide: true,
			children: ($$anchor, $$slotProps) => {
				var fragment_30 = root_40();
				var node_60 = first_child(fragment_30);
				BackTitle(node_60, {
					title: "Подтверждение по email",
					subtitle: "Мы отправили код на user@example.com"
				});
				var div_36 = sibling(node_60, 2);
				each(div_36, 4, () => [
					1,
					2,
					3,
					4,
					5,
					6
				], index, ($$anchor, digit) => {
					var span_10 = root_41$1();
					var text_28 = child(span_10, true);
					reset(span_10);
					template_effect(() => set_text(text_28, digit));
					append($$anchor, span_10);
				});
				reset(div_36);
				var node_61 = sibling(div_36, 2);
				Button(node_61, {
					class: "wide bottom-action",
					children: ($$anchor, $$slotProps) => {
						next();
						append($$anchor, text("Подтвердить"));
					},
					$$slots: { default: true }
				});
				var button = sibling(node_61, 2);
				Refresh_cw(child(button), { size: 15 });
				next();
				reset(button);
				append($$anchor, fragment_30);
			},
			$$slots: { default: true }
		});
		reset(div);
		template_effect(() => set_style(div, (deep_read_state(config()), untrack(() => `--accent: ${config().primaryColor || "#00fe7a"};`))));
		append($$anchor, div);
		pop();
	}
	//#endregion
	//#region bot/app/web/frontend/src/App.svelte
	var root_5 = /* @__PURE__ */ from_html(`<img alt=""/>`);
	var root_6 = /* @__PURE__ */ from_html(`<span> </span>`);
	var root_4 = /* @__PURE__ */ from_html(`<div class="loader"><div class="brand-mark brand-mark-lg"><!></div> <div>Загрузка...</div></div>`);
	var root_10 = /* @__PURE__ */ from_html(`<span> </span>`);
	var root_12 = /* @__PURE__ */ from_html(`<div> </div>`);
	var root_8 = /* @__PURE__ */ from_html(`<header class="screen-head center-title"><!> <div><h1>Подтверждение по email</h1> <p>Мы отправили код на <strong> </strong></p></div> <span></span></header> <div class="otp-wrap"><label class="otp-input-wrap"><input inputmode="numeric" autocomplete="one-time-code" maxlength="6" aria-label="Код подтверждения"/> <span class="otp-slots" aria-hidden="true"></span></label> <!> <!> <button class="link-button" type="button"><!> Отправить код повторно</button></div>`, 1);
	var root_14 = /* @__PURE__ */ from_html(`<img alt=""/>`);
	var root_15 = /* @__PURE__ */ from_html(`<span> </span>`);
	var root_18 = /* @__PURE__ */ from_html(`<!> Код`, 1);
	var root_17 = /* @__PURE__ */ from_html(`<div class="auth-pane"><div class="field-label">Вход по email</div> <div class="email-row"><!> <!></div></div>`);
	var root_21 = /* @__PURE__ */ from_html(`<!> Войти через Telegram`, 1);
	var root_22 = /* @__PURE__ */ from_html(`<div class="telegram-widget"></div>`);
	var root_19 = /* @__PURE__ */ from_html(`<div class="auth-pane"><div class="field-label">Вход через Telegram</div> <!></div>`);
	var root_23 = /* @__PURE__ */ from_html(`<div> </div>`);
	var root_16 = /* @__PURE__ */ from_html(`<div class="segmented"><button type="button">Email</button> <button type="button">Telegram</button></div> <!> <!>`, 1);
	var root_13 = /* @__PURE__ */ from_html(`<div class="auth-card-wrap"><div class="login-brand"><div class="brand-mark brand-mark-xl"><!></div> <h1> </h1> <p>Войдите в свой аккаунт</p></div> <!> <div class="auth-bottom">Нет аккаунта? <strong>Создать</strong></div></div>`);
	var root_7 = /* @__PURE__ */ from_html(`<div class="phone-screen auth-screen"><!></div>`);
	var root_26 = /* @__PURE__ */ from_html(`<img alt=""/>`);
	var root_27 = /* @__PURE__ */ from_html(`<span> </span>`);
	var root_25 = /* @__PURE__ */ from_html(`<header class="app-header accent-title"><div class="brand-row"><div class="brand-mark"><!></div> <strong> </strong></div></header>`);
	var root_29 = /* @__PURE__ */ from_html(`<img alt=""/>`);
	var root_30 = /* @__PURE__ */ from_html(`<span> </span>`);
	var root_31 = /* @__PURE__ */ from_html(`<div class="sub-status"><!> <div><h2> </h2> <p> </p></div></div>`);
	var root_32 = /* @__PURE__ */ from_html(`<div class="traffic-top"><span>Использовано трафика</span> <strong> </strong></div> <div class="progress"><span></span></div> <div class="traffic-percent"> </div>`, 1);
	var root_33 = /* @__PURE__ */ from_html(`<!> Установить и настроить`, 1);
	var root_34 = /* @__PURE__ */ from_html(`<!> Продлить`, 1);
	var root_35 = /* @__PURE__ */ from_html(`<!> Сменить тариф`, 1);
	var root_28 = /* @__PURE__ */ from_html(`<main class="home-layout"><div class="login-brand home-brand"><div class="brand-mark brand-mark-xl"><!></div> <h1> </h1></div> <div class="home-bottom"><!> <!> <div class="action-stack"><!> <!> <!></div></div></main>`);
	var root_38 = /* @__PURE__ */ from_html(`<button type="button"><span class="select-icon"><!></span> <span><strong> </strong> <small> </small> <em> </em></span> <!></button>`);
	var root_41 = /* @__PURE__ */ from_html(`Далее <!>`, 1);
	var root_36 = /* @__PURE__ */ from_html(`<main class="content"><header class="screen-head"><!> <div class="center-copy"><h1>Выбор тарифа</h1> <p>Экраны тарифов пока сверстаны без подключения</p></div> <span></span></header> <div class="tariff-list"></div> <!></main>`);
	var root_45 = /* @__PURE__ */ from_html(`<small> </small>`);
	var root_44 = /* @__PURE__ */ from_html(`<button type="button"><strong> </strong> <span> </span> <!> <!></button>`);
	var root_47 = /* @__PURE__ */ from_html(`<span>Итого<br/><small>К оплате</small></span> <strong> </strong>`, 1);
	var root_49 = /* @__PURE__ */ from_html(`<button type="button"><!> <span><strong> </strong> <small> </small></span></button>`);
	var root_52 = /* @__PURE__ */ from_html(` <!>`, 1);
	var root_42 = /* @__PURE__ */ from_html(`<main class="content"><header class="screen-head"><!> <div class="center-copy"><h1>Подписка</h1> <p>Выберите срок подписки</p></div> <span></span></header> <div class="period-grid"></div> <!> <div class="method-grid"><!></div> <!></main>`);
	var root_55 = /* @__PURE__ */ from_html(`<button type="button"><strong> </strong> <span> </span> <small> </small> <!></button>`);
	var root_57 = /* @__PURE__ */ from_html(`<span>Итого<br/><small>К оплате</small></span> <strong> </strong>`, 1);
	var root_58 = /* @__PURE__ */ from_html(`<button class="method-card" type="button"><!> <span><strong> </strong> <small> </small></span></button>`);
	var root_59 = /* @__PURE__ */ from_html(` <!>`, 1);
	var root_53 = /* @__PURE__ */ from_html(`<main class="content"><header class="screen-head"><!> <div class="center-copy"><h1>Трафик</h1> <p>Выберите пакет трафика</p></div> <span></span></header> <div class="period-grid"></div> <!> <div class="method-grid"></div> <!></main>`);
	var root_62 = /* @__PURE__ */ from_html(`<button type="button"><span><strong> </strong> <small> </small></span> <em> </em> <!></button>`);
	var root_65 = /* @__PURE__ */ from_html(`Далее <!>`, 1);
	var root_60 = /* @__PURE__ */ from_html(`<main class="content"><header class="screen-head"><!> <div class="center-copy"><h1>Смена тарифа</h1> <p>Остаток 12 дней будет пересчитан</p></div> <span></span></header> <div class="tariff-list compact"></div> <!></main>`);
	var root_68 = /* @__PURE__ */ from_html(`Копировать <!>`, 1);
	var root_67 = /* @__PURE__ */ from_html(`<div class="card-label">Ваша реферальная ссылка</div> <div class="copy-row"><code> </code> <!></div>`, 1);
	var root_69 = /* @__PURE__ */ from_html(`<!> <div><span>Ваш бонус</span> <strong>+7 дней за каждого друга</strong> <p>Друг получит +3 дня к подписке после регистрации.</p></div>`, 1);
	var root_71 = /* @__PURE__ */ from_html(`<!> Активировать`, 1);
	var root_72 = /* @__PURE__ */ from_html(`<p> </p>`);
	var root_70 = /* @__PURE__ */ from_html(`<div class="card-label">Промокод</div> <div class="copy-row"><!> <!></div> <!>`, 1);
	var root_66 = /* @__PURE__ */ from_html(`<main class="content with-nav"><!> <!> <!></main>`);
	var root_75 = /* @__PURE__ */ from_html(`<img alt="Аватар пользователя" loading="lazy" referrerpolicy="no-referrer"/>`);
	var root_74 = /* @__PURE__ */ from_html(`<div class="settings-avatar"><!></div> <div class="settings-profile-meta"><strong> </strong> <small> </small> <small> </small></div>`, 1);
	var root_73 = /* @__PURE__ */ from_html(`<main class="content with-nav"><!> <div class="settings-list"><button class="settings-row" type="button"><!> <span><strong>Выбор языка</strong><small> </small></span> <!></button> <button class="settings-row" type="button"><!> <span><strong>Привязка Telegram</strong><small> </small></span> <!></button> <button class="settings-row" type="button"><!> <span><strong>Привязка почты</strong><small> </small></span> <!></button> <button class="settings-row" type="button"><!> <span><strong>Выйти</strong><small>Завершить сессию</small></span> <!></button></div></main>`);
	var root_77 = /* @__PURE__ */ from_html(`<nav class="bottom-nav" aria-label="Навигация"><button type="button"><!> <span>Главная</span></button> <button type="button"><!> <span>Пригласить</span></button> <button type="button"><!> <span>Настройки</span></button></nav>`);
	var root_24 = /* @__PURE__ */ from_html(`<div class="phone-screen"><!> <!> <!></div>`);
	var root_78 = /* @__PURE__ */ from_html(`<div class="dialog-actions"><!> <!></div>`);
	var root_81 = /* @__PURE__ */ from_html(`<div class="toast" role="status"> </div>`);
	var root_3 = /* @__PURE__ */ from_html(`<div class="app-shell"><!> <!> <!></div>`);
	function App($$anchor, $$props) {
		push($$props, false);
		const brandTitle = /* @__PURE__ */ mutable_source();
		const brandEmoji = /* @__PURE__ */ mutable_source();
		const accent = /* @__PURE__ */ mutable_source();
		const plans = /* @__PURE__ */ mutable_source();
		const methods = /* @__PURE__ */ mutable_source();
		const subscription = /* @__PURE__ */ mutable_source();
		const user = /* @__PURE__ */ mutable_source();
		const referral = /* @__PURE__ */ mutable_source();
		const userLanguage = /* @__PURE__ */ mutable_source();
		const telegramProfileName = /* @__PURE__ */ mutable_source();
		const profileEmail = /* @__PURE__ */ mutable_source();
		const profileTelegramId = /* @__PURE__ */ mutable_source();
		const profileAvatarUrl = /* @__PURE__ */ mutable_source();
		const TELEGRAM_LOGIN_WIDGET_URL = "https://telegram.org/js/telegram-widget.js?23";
		const TELEGRAM_LOGIN_WIDGET_RENDER_TIMEOUT_MS = 8e3;
		const MANUAL_LOGOUT_FLAG_KEY = "rw_webapp_manual_logout";
		const LANGUAGE_LABELS = {
			ru: "Русский",
			en: "English",
			de: "Deutsch",
			es: "Español",
			fr: "Français",
			tr: "Türkçe",
			uk: "Українська"
		};
		const DEV_MOCK = {
			config: {
				title: "/minishop",
				primaryColor: "#00fe7a",
				logoUrl: "",
				logoEmoji: "🫥",
				apiBase: "/api",
				supportUrl: "https://t.me/support",
				privacyPolicyUrl: "https://example.com/privacy",
				userAgreementUrl: "https://example.com/agreement",
				currency: "RUB",
				language: "ru",
				emailAuthEnabled: true,
				telegramLoginBotUsername: "preview_bot"
			},
			data: {
				ok: true,
				user: {
					id: 100200300,
					username: "username",
					email: "user@example.com",
					email_verified: true,
					telegram_id: 100200300,
					telegram_linked: true,
					telegram_photo_url: "",
					first_name: "Preview",
					language_code: "ru"
				},
				subscription: {
					active: true,
					status: "ACTIVE",
					remaining_text: "25 д. 8 ч.",
					end_date_text: "24.05.2026",
					days_left: 25,
					config_link: "https://sub.example.com/sub/preview-token",
					connect_url: "https://sub.example.com/connect/preview-token",
					traffic_used: "18.4 GB",
					traffic_limit: "100 GB",
					traffic_used_bytes: 19756849561,
					traffic_limit_bytes: 107374182400
				},
				plans: [
					{
						months: 1,
						price: 290,
						currency: "RUB",
						title: "1 месяц"
					},
					{
						months: 3,
						price: 790,
						currency: "RUB",
						title: "3 месяца"
					},
					{
						months: 6,
						price: 1490,
						currency: "RUB",
						title: "6 месяцев"
					},
					{
						months: 12,
						price: 2690,
						currency: "RUB",
						title: "12 месяцев"
					}
				],
				payment_methods: [
					{
						id: "yookassa",
						name: "Карта"
					},
					{
						id: "platega_sbp",
						name: "Telegram Pay"
					},
					{
						id: "cryptopay",
						name: "Криптовалюта"
					},
					{
						id: "freekassa",
						name: "Другие способы"
					}
				],
				referral: {
					code: "ABCD1234",
					bot_link: "https://t.me/preview_bot?start=ref_uABCD1234",
					webapp_link: "https://minishop.app/ref/ABCD1234",
					invited_count: 4,
					purchased_count: 2,
					bonus_details: [{
						months: 1,
						title: "1 месяц",
						inviter_days: 7,
						friend_days: 3
					}, {
						months: 3,
						title: "3 месяца",
						inviter_days: 14,
						friend_days: 7
					}]
				},
				settings: {
					support_url: "https://t.me/support",
					traffic_mode: false,
					email_auth_enabled: true
				}
			}
		};
		const demoTariffs = [
			{
				id: "subscription",
				title: "Подписка",
				caption: "Безлимитный трафик",
				details: "Идеально для постоянного использования",
				icon: "infinity",
				billing: "period"
			},
			{
				id: "traffic",
				title: "Трафик",
				caption: "Пакеты гигабайт",
				details: "Платите только за нужный объем",
				icon: "database",
				billing: "traffic"
			},
			{
				id: "premium",
				title: "Премиум",
				caption: "Максимальная скорость",
				details: "Приоритетные серверы и поддержка",
				icon: "crown",
				billing: "period"
			}
		];
		const trafficPackages = [
			{
				gb: 20,
				price: 290
			},
			{
				gb: 50,
				price: 590
			},
			{
				gb: 100,
				price: 990
			},
			{
				gb: 300,
				price: 2190
			}
		];
		const changeTariffs = [
			{
				...demoTariffs[0],
				recalculation: "Доплата 190 ₽"
			},
			{
				...demoTariffs[1],
				recalculation: "Доплата не требуется"
			},
			{
				...demoTariffs[2],
				recalculation: "Доплата 390 ₽"
			}
		];
		const isPreviewBoard = new URLSearchParams(window.location.search).get("preview") === "all";
		const injectedConfig = readJsonScript("webapp-config");
		const isLocalShell = window.location.protocol === "file:" || [
			"",
			"localhost",
			"127.0.0.1"
		].includes(window.location.hostname);
		const MOCK = !injectedConfig && isLocalShell ? DEV_MOCK : null;
		const CFG = {
			...DEV_MOCK.config,
			...MOCK ? MOCK.config : {},
			...injectedConfig || {}
		};
		const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
		let mode = /* @__PURE__ */ mutable_source(isPreviewBoard ? "preview" : "loading");
		let activeTab = /* @__PURE__ */ mutable_source("home");
		let screen = /* @__PURE__ */ mutable_source("home");
		let data = /* @__PURE__ */ mutable_source(isPreviewBoard ? structuredCloneSafe(DEV_MOCK.data) : null);
		let selectedTariff = /* @__PURE__ */ mutable_source("subscription");
		let selectedChangeTariff = /* @__PURE__ */ mutable_source("traffic");
		let selectedPlan = /* @__PURE__ */ mutable_source(null);
		let selectedTrafficPackage = /* @__PURE__ */ mutable_source(trafficPackages[2]);
		let selectedMethod = /* @__PURE__ */ mutable_source("");
		let payBusy = /* @__PURE__ */ mutable_source(false);
		let promoCode = /* @__PURE__ */ mutable_source("");
		let promoBusy = /* @__PURE__ */ mutable_source(false);
		let promoStatus = /* @__PURE__ */ mutable_source("");
		let promoIsError = /* @__PURE__ */ mutable_source(false);
		let toastText = /* @__PURE__ */ mutable_source("");
		let toastTimer = null;
		let authMode = /* @__PURE__ */ mutable_source(CFG.emailAuthEnabled === false ? "telegram" : "email");
		let authStatus = /* @__PURE__ */ mutable_source("");
		let authIsError = /* @__PURE__ */ mutable_source(false);
		let authBusy = /* @__PURE__ */ mutable_source(false);
		let email = /* @__PURE__ */ mutable_source("");
		let pendingEmail = /* @__PURE__ */ mutable_source("");
		let emailCode = /* @__PURE__ */ mutable_source("");
		let emailAvatarUrl = /* @__PURE__ */ mutable_source("");
		let avatarHashToken = /* @__PURE__ */ mutable_source("");
		let loginTelegramNode = /* @__PURE__ */ mutable_source();
		let token = MOCK ? "local-preview" : localStorage.getItem("rw_webapp_token") || "";
		let csrfToken = MOCK ? "" : readCookie("rw_webapp_csrf") || "";
		let confirmTariffOpen = /* @__PURE__ */ mutable_source(false);
		onMount(() => {
			if (isPreviewBoard) return;
			boot();
		});
		function readJsonScript(id) {
			const node = document.getElementById(id);
			if (!node || !node.textContent) return null;
			try {
				return JSON.parse(node.textContent);
			} catch (error) {
				console.warn(`Failed to parse JSON config from #${id}`, error);
				return null;
			}
		}
		function structuredCloneSafe(value) {
			try {
				return structuredClone(value);
			} catch {
				return JSON.parse(JSON.stringify(value));
			}
		}
		async function boot() {
			set(mode, "loading");
			if (tg) try {
				tg.ready();
				tg.expand();
			} catch {}
			if (MOCK) {
				await loadData();
				return;
			}
			const magicToken = readMagicLoginToken();
			if (magicToken && await finalizeMagicLogin(magicToken)) return;
			if (isManuallyLoggedOut()) {
				showLogin();
				return;
			}
			const widgetAuthData = readTelegramLoginWidgetAuthData();
			if (widgetAuthData && await finalizeTelegramAuth(widgetAuthData, "auth_data")) return;
			if (tg?.initData) try {
				if (await finalizeTelegramAuth(tg.initData, "init_data")) return;
			} catch {}
			if (token || csrfToken) try {
				await loadData();
				return;
			} catch {
				clearToken();
			}
			showLogin();
		}
		async function loadData() {
			const payload = await api("/me");
			if (!payload.ok) throw new Error(payload.error || "load_failed");
			set(data, payload);
			set(selectedPlan, payload.plans?.[Math.min(1, payload.plans.length - 1)] || payload.plans?.[0] || null);
			set(selectedMethod, payload.payment_methods?.[0]?.id || "");
			set(screen, "home");
			set(mode, "app");
		}
		function showLogin() {
			set(mode, "login");
			set(screen, "login");
			set(activeTab, "home");
			renderTelegramWidgetWhenNeeded();
		}
		async function api(path, options = {}) {
			if (MOCK) return mockApi(path, options);
			const method = String(options.method || "GET").toUpperCase();
			const headers = { ...options.headers || {} };
			if (token) headers.Authorization = `Bearer ${token}`;
			const csrf = csrfToken || readCookie("rw_webapp_csrf") || "";
			if (csrf && [
				"POST",
				"PUT",
				"PATCH",
				"DELETE"
			].includes(method)) headers["X-CSRF-Token"] = csrf;
			if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
			const response = await fetch(`${CFG.apiBase}${path}`, {
				...options,
				headers
			});
			const payload = await response.json().catch(() => ({}));
			if (response.status === 401) {
				clearToken();
				showLogin();
			}
			return payload;
		}
		async function publicApi(path, payload = {}) {
			if (MOCK) return mockApi(path, {
				method: "POST",
				body: JSON.stringify(payload)
			});
			return (await fetch(`${CFG.apiBase}${path}`, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify(payload)
			})).json();
		}
		async function mockApi(path, options = {}) {
			await new Promise((resolve) => window.setTimeout(resolve, 120));
			if (path === "/me") return structuredCloneSafe(DEV_MOCK.data);
			if (path === "/auth/email/request") return { ok: true };
			if (path === "/auth/email/verify" || path === "/auth/email/magic") return {
				ok: true,
				token: "local-preview",
				csrf_token: "local-preview-csrf"
			};
			if (path === "/auth/token") return {
				ok: true,
				token: "local-preview",
				csrf_token: "local-preview-csrf"
			};
			if (path === "/promo/apply") return {
				ok: true,
				end_date_text: "31.05.2026"
			};
			if (path === "/auth/logout") return { ok: true };
			if (path === "/payments" && String(options.method || "").toUpperCase() === "POST") return {
				ok: true,
				action: "open_link",
				payment_url: "https://example.com/payment-preview",
				payment_id: 10001
			};
			return {
				ok: false,
				error: "not_found"
			};
		}
		function readCookie(name) {
			const prefix = `${name}=`;
			const cookie = document.cookie.split("; ").find((part) => part.startsWith(prefix));
			return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : "";
		}
		function setToken(nextToken, nextCsrf = "") {
			clearManualLogoutFlag();
			token = nextToken || "";
			csrfToken = nextCsrf || readCookie("rw_webapp_csrf") || "";
			if (token && !MOCK) localStorage.setItem("rw_webapp_token", token);
		}
		function clearToken() {
			token = "";
			csrfToken = "";
			localStorage.removeItem("rw_webapp_token");
		}
		function markManualLogout() {
			try {
				localStorage.setItem(MANUAL_LOGOUT_FLAG_KEY, "1");
			} catch {}
		}
		function clearManualLogoutFlag() {
			try {
				localStorage.removeItem(MANUAL_LOGOUT_FLAG_KEY);
			} catch {}
		}
		function isManuallyLoggedOut() {
			try {
				return localStorage.getItem(MANUAL_LOGOUT_FLAG_KEY) === "1";
			} catch {
				return false;
			}
		}
		function readReferralParam() {
			const params = new URLSearchParams(window.location.search);
			const fromQuery = params.get("ref") || params.get("start") || params.get("start_param") || "";
			const fromTelegram = tg?.initDataUnsafe?.start_param || "";
			const value = String(fromTelegram || fromQuery || "").trim();
			if (value) {
				localStorage.setItem("rw_webapp_referral", value);
				return value;
			}
			return localStorage.getItem("rw_webapp_referral") || "";
		}
		function readMagicLoginToken() {
			return (new URLSearchParams(window.location.search).get("login_token") || "").trim() || null;
		}
		function readTelegramLoginWidgetAuthData() {
			const params = new URLSearchParams(window.location.search);
			const keys = [
				"id",
				"first_name",
				"last_name",
				"username",
				"photo_url",
				"auth_date",
				"hash"
			];
			const authData = {};
			let hasAuthValue = false;
			keys.forEach((key) => {
				if (!params.has(key)) return;
				authData[key] = params.get(key) || "";
				hasAuthValue = true;
			});
			if (!hasAuthValue || !authData.id || !authData.auth_date || !authData.hash) return null;
			return authData;
		}
		function clearAuthQuery() {
			const url = new URL(window.location.href);
			[
				"login_token",
				"login_purpose",
				"id",
				"first_name",
				"last_name",
				"username",
				"photo_url",
				"auth_date",
				"hash"
			].forEach((key) => url.searchParams.delete(key));
			window.history?.replaceState?.({}, document.title, url.pathname + url.search + url.hash);
		}
		async function finalizeMagicLogin(loginToken) {
			if (get(authBusy)) return false;
			set(authBusy, true);
			setAuthStatus("Проверяем вход...");
			try {
				const payload = { token: loginToken };
				const referralParam = readReferralParam();
				if (referralParam) payload.referral_code = referralParam;
				const response = await publicApi("/auth/email/magic", payload);
				if (response.ok && response.token) {
					setToken(response.token, response.csrf_token);
					clearAuthQuery();
					await loadData();
					return true;
				}
				setAuthStatus("Не удалось подтвердить вход", true);
			} catch {
				setAuthStatus("Не удалось подтвердить вход", true);
			} finally {
				set(authBusy, false);
			}
			return false;
		}
		async function finalizeTelegramAuth(authData, source = "auth_data") {
			if (get(authBusy)) return false;
			set(authBusy, true);
			setAuthStatus("Проверяем Telegram...");
			try {
				const payload = source === "init_data" ? { init_data: authData } : { auth_data: authData };
				const referralParam = readReferralParam();
				if (referralParam) payload.referral_code = referralParam;
				const response = await publicApi("/auth/token", payload);
				if (response.ok && response.token) {
					setToken(response.token, response.csrf_token);
					clearAuthQuery();
					setAuthStatus("");
					await loadData();
					return true;
				}
				setAuthStatus(response.error === "banned" ? "Доступ запрещен" : "Telegram-вход не подтвержден", true);
			} catch {
				setAuthStatus("Telegram-вход сейчас недоступен", true);
			} finally {
				set(authBusy, false);
			}
			return false;
		}
		async function requestEmailCode() {
			const normalized = get(email).trim().toLowerCase();
			if (!normalized || !normalized.includes("@")) {
				setAuthStatus("Введите корректный email", true);
				return;
			}
			set(authBusy, true);
			setAuthStatus("Отправляем код...");
			try {
				const payload = {
					email: normalized,
					language: "ru"
				};
				const referralParam = readReferralParam();
				if (referralParam) payload.referral_code = referralParam;
				const response = await publicApi("/auth/email/request", payload);
				if (!response.ok) throw response;
				set(pendingEmail, normalized);
				set(emailCode, "");
				set(screen, "code");
				set(mode, "login");
				setAuthStatus("");
			} catch (error) {
				setAuthStatus(emailError(error, "Не удалось отправить код"), true);
			} finally {
				set(authBusy, false);
			}
		}
		async function verifyEmailCode() {
			const code = get(emailCode).replace(/\D/g, "").slice(0, 6);
			if (code.length !== 6) {
				setAuthStatus("Введите 6 цифр из письма", true);
				return;
			}
			set(authBusy, true);
			setAuthStatus("Проверяем код...");
			try {
				const payload = {
					email: get(pendingEmail),
					code
				};
				const referralParam = readReferralParam();
				if (referralParam) payload.referral_code = referralParam;
				const response = await publicApi("/auth/email/verify", payload);
				if (!response.ok || !response.token) throw response;
				setToken(response.token, response.csrf_token);
				await loadData();
				setAuthStatus("");
			} catch (error) {
				setAuthStatus(emailError(error, "Неверный код"), true);
			} finally {
				set(authBusy, false);
			}
		}
		function emailError(error, fallback) {
			if (error?.error === "rate_limited") return `Повторная отправка через ${error.retry_after || 60} сек.`;
			if (error?.error === "invalid_email") return "Введите корректный email";
			if (error?.error === "expired_code") return "Код устарел";
			if (error?.error === "invalid_code" || error?.error === "too_many_attempts") return "Неверный код";
			return fallback;
		}
		function setAuthStatus(message, isError = false) {
			set(authStatus, message);
			set(authIsError, isError);
		}
		async function renderTelegramWidgetWhenNeeded() {
			await tick();
			if (get(authMode) !== "telegram" || !get(loginTelegramNode)) return;
			mutate(loginTelegramNode, get(loginTelegramNode).innerHTML = "");
			if (tg?.initData) return;
			const botUsername = String(CFG.telegramLoginBotUsername || "").trim();
			if (!botUsername) {
				setAuthStatus("Telegram Login Widget не настроен", true);
				return;
			}
			window.onTelegramAuth = async (telegramUser) => {
				await finalizeTelegramAuth(telegramUser, "auth_data");
			};
			appendTelegramLoginWidget(get(loginTelegramNode), botUsername, "onTelegramAuth", () => setAuthStatus("Telegram Login Widget сейчас недоступен", true));
		}
		function appendTelegramLoginWidget(container, botUsername, callbackName, onUnavailable) {
			const script = document.createElement("script");
			let unavailableShown = false;
			const showUnavailable = () => {
				if (unavailableShown) return;
				unavailableShown = true;
				onUnavailable();
			};
			script.async = true;
			script.src = TELEGRAM_LOGIN_WIDGET_URL;
			script.setAttribute("data-telegram-login", botUsername);
			script.setAttribute("data-size", "large");
			script.setAttribute("data-userpic", "true");
			script.setAttribute("data-request-access", "write");
			script.setAttribute("data-onauth", `${callbackName}(user)`);
			script.onerror = showUnavailable;
			script.onload = () => {
				window.setTimeout(() => {
					if (!container.contains(script) || container.querySelector("iframe")) return;
					showUnavailable();
				}, TELEGRAM_LOGIN_WIDGET_RENDER_TIMEOUT_MS);
			};
			container.appendChild(script);
		}
		async function openTelegramLogin() {
			set(authMode, "telegram");
			if (tg?.initData) {
				await finalizeTelegramAuth(tg.initData, "init_data");
				return;
			}
			renderTelegramWidgetWhenNeeded();
		}
		async function createPayment() {
			if (!get(selectedPlan) || !get(selectedMethod) || get(payBusy)) return;
			set(payBusy, true);
			try {
				const response = await api("/payments", {
					method: "POST",
					body: JSON.stringify({
						months: get(selectedPlan).months,
						method: get(selectedMethod)
					})
				});
				if (!response.ok || !response.payment_url) throw response;
				showToast("Платеж создан");
				openExternalLink(response.payment_url);
			} catch (error) {
				showToast(error?.message || "Не удалось создать платеж");
			} finally {
				set(payBusy, false);
			}
		}
		function openExternalLink(url) {
			if (!url) return;
			if (tg?.openLink) tg.openLink(url);
			else window.open(url, "_blank", "noopener");
		}
		function openConnectLink() {
			const url = get(subscription)?.connect_url || get(subscription)?.config_link;
			if (!url) {
				showToast("Ссылка для подключения пока недоступна");
				return;
			}
			openExternalLink(url);
		}
		async function copyText(value, success = "Скопировано") {
			if (!value) {
				showToast("Пока недоступно");
				return;
			}
			try {
				await navigator.clipboard.writeText(value);
			} catch {
				const area = document.createElement("textarea");
				area.value = value;
				document.body.appendChild(area);
				area.select();
				document.execCommand("copy");
				area.remove();
			}
			showToast(success);
		}
		async function applyPromo() {
			const code = get(promoCode).trim();
			if (!code) {
				set(promoStatus, "Введите промокод");
				set(promoIsError, true);
				return;
			}
			set(promoBusy, true);
			set(promoStatus, "");
			try {
				const response = await api("/promo/apply", {
					method: "POST",
					body: JSON.stringify({ code })
				});
				if (!response.ok) throw response;
				set(promoCode, "");
				set(promoStatus, response.end_date_text ? `Промокод активирован. Подписка до ${response.end_date_text}` : "Промокод активирован");
				set(promoIsError, false);
				await loadData();
			} catch (error) {
				set(promoStatus, error?.message || "Не удалось активировать промокод");
				set(promoIsError, true);
			} finally {
				set(promoBusy, false);
			}
		}
		async function logout() {
			markManualLogout();
			clearToken();
			try {
				await publicApi("/auth/logout", { keepalive: true });
			} catch {}
			showLogin();
		}
		function showToast(message) {
			set(toastText, message);
			if (toastTimer) window.clearTimeout(toastTimer);
			toastTimer = window.setTimeout(() => {
				set(toastText, "");
			}, 2400);
		}
		function goHome() {
			set(activeTab, "home");
			set(screen, "home");
		}
		function goInvite() {
			set(activeTab, "invite");
			set(screen, "invite");
		}
		function goSettings() {
			set(activeTab, "settings");
			set(screen, "settings");
		}
		function methodMeta(method) {
			const id = String(method?.id || "").toLowerCase();
			if (id.includes("yookassa") || id.includes("card")) return {
				title: method.name || "Карта",
				note: "Visa, Mastercard",
				icon: Credit_card
			};
			if (id.includes("platega") || id.includes("sbp")) return {
				title: method.name || "СБП",
				note: "Быстро и удобно",
				icon: Send
			};
			if (id.includes("crypto")) return {
				title: method.name || "Криптовалюта",
				note: "USDT, BTC, ETH",
				icon: Wallet_cards
			};
			if (id.includes("stars")) return {
				title: "Telegram Stars",
				note: "Оплата звездами",
				icon: Zap
			};
			return {
				title: method.name || "Другие способы",
				note: "ЮMoney, СБП и др.",
				icon: Wallet_cards
			};
		}
		function formatMoney(value, currency = CFG.currency || "RUB") {
			const numeric = Number(value || 0);
			return `${Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(2)} ${currency === "RUB" ? "₽" : currency}`;
		}
		function trafficPercent(sub) {
			const used = Number(sub?.traffic_used_bytes || 0);
			const limit = Number(sub?.traffic_limit_bytes || 0);
			if (!limit || limit <= 0) return 100;
			return Math.max(0, Math.min(100, Math.round(used / limit * 100)));
		}
		function trafficLabel(sub) {
			if (!sub?.traffic_limit_bytes || Number(sub.traffic_limit_bytes) <= 0) return "Безлимитный трафик";
			return `${sub.traffic_used || "0 GB"} из ${sub.traffic_limit || "0 GB"}`;
		}
		function normalizedEmail(value) {
			return String(value || "").trim().toLowerCase();
		}
		function languageName(code) {
			const key = String(code || "").trim().toLowerCase();
			if (!key) return "Русский";
			return LANGUAGE_LABELS[key] || key.toUpperCase();
		}
		function telegramName(profile) {
			const first = String(profile?.first_name || "").trim();
			const last = String(profile?.last_name || "").trim();
			if (first || last) return `${first} ${last}`.trim();
			const username = String(profile?.username || "").trim();
			if (username) return `@${username}`;
			return "Telegram не привязан";
		}
		function bytesToHex(buffer) {
			return Array.from(new Uint8Array(buffer), (byte) => byte.toString(16).padStart(2, "0")).join("");
		}
		async function sha256Hex(value) {
			const data = new TextEncoder().encode(value);
			return bytesToHex(await window.crypto.subtle.digest("SHA-256", data));
		}
		async function buildGravatarUrl(emailValue) {
			if (!emailValue || !window.crypto?.subtle) return "";
			try {
				return `https://www.gravatar.com/avatar/${await sha256Hex(emailValue)}?d=mp&s=160`;
			} catch {
				return "";
			}
		}
		function tariffIcon(id) {
			if (id === "traffic") return Database;
			if (id === "premium") return Crown;
			return Zap;
		}
		legacy_pre_effect(() => {}, () => {
			set(brandTitle, CFG.title || "/minishop");
		});
		legacy_pre_effect(() => {}, () => {
			set(brandEmoji, CFG.logoEmoji || "🫥");
		});
		legacy_pre_effect(() => {}, () => {
			set(accent, CFG.primaryColor || "#00fe7a");
		});
		legacy_pre_effect(() => get(data), () => {
			set(plans, get(data)?.plans?.length ? get(data).plans : DEV_MOCK.data.plans);
		});
		legacy_pre_effect(() => get(data), () => {
			set(methods, get(data)?.payment_methods?.length ? get(data).payment_methods : []);
		});
		legacy_pre_effect(() => get(data), () => {
			set(subscription, get(data)?.subscription || DEV_MOCK.data.subscription);
		});
		legacy_pre_effect(() => get(data), () => {
			set(user, get(data)?.user || {});
		});
		legacy_pre_effect(() => get(data), () => {
			set(referral, get(data)?.referral || DEV_MOCK.data.referral);
		});
		legacy_pre_effect(() => get(user), () => {
			set(userLanguage, languageName(get(user)?.language_code || CFG.language || "ru"));
		});
		legacy_pre_effect(() => get(user), () => {
			set(telegramProfileName, telegramName(get(user)));
		});
		legacy_pre_effect(() => get(user), () => {
			set(profileEmail, get(user)?.email || "Почта не привязана");
		});
		legacy_pre_effect(() => get(user), () => {
			set(profileTelegramId, get(user)?.telegram_id ? `TG ID ${get(user).telegram_id}` : "TG ID не привязан");
		});
		legacy_pre_effect(() => (get(user), get(avatarHashToken)), () => {
			const emailKey = normalizedEmail(get(user)?.email);
			if (!emailKey) {
				set(avatarHashToken, "");
				set(emailAvatarUrl, "");
			} else if (get(avatarHashToken) !== emailKey) {
				set(avatarHashToken, emailKey);
				buildGravatarUrl(emailKey).then((url) => {
					if (get(avatarHashToken) === emailKey) set(emailAvatarUrl, url);
				});
			}
		});
		legacy_pre_effect(() => (get(user), get(emailAvatarUrl)), () => {
			set(profileAvatarUrl, get(user)?.telegram_photo_url || get(emailAvatarUrl) || "");
		});
		legacy_pre_effect(() => (get(selectedPlan), get(plans)), () => {
			if (!get(selectedPlan) && get(plans).length) set(selectedPlan, get(plans)[Math.min(1, get(plans).length - 1)]);
		});
		legacy_pre_effect(() => (get(selectedMethod), get(methods)), () => {
			if (!get(selectedMethod) && get(methods).length) set(selectedMethod, get(methods)[0].id);
		});
		legacy_pre_effect_reset();
		init();
		var fragment = comment();
		head("150dgq4", ($$anchor) => {
			deferred_template_effect(() => {
				$document.title = get(brandTitle) ?? "";
			});
		});
		var node_1 = first_child(fragment);
		var consequent = ($$anchor) => {
			PreviewBoard($$anchor, {
				get config() {
					return CFG;
				},
				get mockData() {
					return untrack(() => DEV_MOCK.data);
				}
			});
		};
		var alternate_12 = ($$anchor) => {
			var div = root_3();
			var node_2 = child(div);
			var consequent_2 = ($$anchor) => {
				var div_1 = root_4();
				var div_2 = child(div_1);
				var node_3 = child(div_2);
				var consequent_1 = ($$anchor) => {
					var img = root_5();
					template_effect(() => set_attribute(img, "src", untrack(() => CFG.logoUrl)));
					append($$anchor, img);
				};
				var alternate = ($$anchor) => {
					var span = root_6();
					var text = child(span, true);
					reset(span);
					template_effect(() => set_text(text, get(brandEmoji)));
					append($$anchor, span);
				};
				if_block(node_3, ($$render) => {
					if (untrack(() => CFG.logoUrl)) $$render(consequent_1);
					else $$render(alternate, -1);
				});
				reset(div_2);
				next(2);
				reset(div_1);
				append($$anchor, div_1);
			};
			var consequent_9 = ($$anchor) => {
				var div_3 = root_7();
				var node_4 = child(div_3);
				var consequent_4 = ($$anchor) => {
					var fragment_2 = root_8();
					var header = first_child(fragment_2);
					var node_5 = child(header);
					Button(node_5, {
						variant: "icon",
						size: "icon",
						onclick: () => set(screen, "login"),
						"aria-label": "Назад",
						children: ($$anchor, $$slotProps) => {
							Arrow_left($$anchor, { size: 19 });
						},
						$$slots: { default: true }
					});
					var div_4 = sibling(node_5, 2);
					var p = sibling(child(div_4), 2);
					var strong = sibling(child(p));
					var text_1 = child(strong, true);
					reset(strong);
					reset(p);
					reset(div_4);
					next(2);
					reset(header);
					var div_5 = sibling(header, 2);
					var label = child(div_5);
					var input = child(label);
					remove_input_defaults(input);
					var span_1 = sibling(input, 2);
					each(span_1, 4, () => untrack(() => Array.from({ length: 6 })), index, ($$anchor, _, index) => {
						var span_2 = root_10();
						let classes;
						var text_2 = child(span_2, true);
						reset(span_2);
						template_effect(() => {
							classes = set_class(span_2, 1, "", null, classes, { filled: get(emailCode)[index] });
							set_text(text_2, (get(emailCode), untrack(() => get(emailCode)[index] || "")));
						});
						append($$anchor, span_2);
					});
					reset(span_1);
					reset(label);
					var node_6 = sibling(label, 2);
					Button(node_6, {
						class: "wide",
						onclick: verifyEmailCode,
						get disabled() {
							return get(authBusy);
						},
						children: ($$anchor, $$slotProps) => {
							next();
							append($$anchor, text("Подтвердить"));
						},
						$$slots: { default: true }
					});
					var node_7 = sibling(node_6, 2);
					var consequent_3 = ($$anchor) => {
						var div_6 = root_12();
						let classes_1;
						var text_4 = child(div_6, true);
						reset(div_6);
						template_effect(() => {
							classes_1 = set_class(div_6, 1, "status-line", null, classes_1, { error: get(authIsError) });
							set_text(text_4, get(authStatus));
						});
						append($$anchor, div_6);
					};
					if_block(node_7, ($$render) => {
						if (get(authStatus)) $$render(consequent_3);
					});
					var button = sibling(node_7, 2);
					Refresh_cw(child(button), { size: 15 });
					next();
					reset(button);
					reset(div_5);
					template_effect(() => {
						set_text(text_1, get(pendingEmail));
						button.disabled = get(authBusy);
					});
					bind_value(input, () => get(emailCode), ($$value) => set(emailCode, $$value));
					event("click", button, requestEmailCode);
					append($$anchor, fragment_2);
				};
				var alternate_4 = ($$anchor) => {
					var div_7 = root_13();
					var div_8 = child(div_7);
					var div_9 = child(div_8);
					var node_9 = child(div_9);
					var consequent_5 = ($$anchor) => {
						var img_1 = root_14();
						template_effect(() => set_attribute(img_1, "src", untrack(() => CFG.logoUrl)));
						append($$anchor, img_1);
					};
					var alternate_1 = ($$anchor) => {
						var span_3 = root_15();
						var text_5 = child(span_3, true);
						reset(span_3);
						template_effect(() => set_text(text_5, get(brandEmoji)));
						append($$anchor, span_3);
					};
					if_block(node_9, ($$render) => {
						if (untrack(() => CFG.logoUrl)) $$render(consequent_5);
						else $$render(alternate_1, -1);
					});
					reset(div_9);
					var h1 = sibling(div_9, 2);
					var text_6 = child(h1, true);
					reset(h1);
					next(2);
					reset(div_8);
					Card(sibling(div_8, 2), {
						class: "auth-card",
						children: ($$anchor, $$slotProps) => {
							var fragment_4 = root_16();
							var div_10 = first_child(fragment_4);
							var button_1 = child(div_10);
							let classes_2;
							var button_2 = sibling(button_1, 2);
							let classes_3;
							reset(div_10);
							var node_11 = sibling(div_10, 2);
							var consequent_6 = ($$anchor) => {
								var div_11 = root_17();
								var div_12 = sibling(child(div_11), 2);
								var node_12 = child(div_12);
								Input(node_12, {
									type: "email",
									placeholder: "Email",
									autocomplete: "email",
									get value() {
										return get(email);
									},
									set value($$value) {
										set(email, $$value);
									},
									$$legacy: true
								});
								Button(sibling(node_12, 2), {
									variant: "outline",
									onclick: requestEmailCode,
									get disabled() {
										return get(authBusy);
									},
									children: ($$anchor, $$slotProps) => {
										var fragment_5 = root_18();
										Mail(first_child(fragment_5), { size: 18 });
										next();
										append($$anchor, fragment_5);
									},
									$$slots: { default: true }
								});
								reset(div_12);
								reset(div_11);
								append($$anchor, div_11);
							};
							var alternate_3 = ($$anchor) => {
								var div_13 = root_19();
								var node_15 = sibling(child(div_13), 2);
								var consequent_7 = ($$anchor) => {
									Button($$anchor, {
										variant: "telegram",
										onclick: openTelegramLogin,
										get disabled() {
											return get(authBusy);
										},
										children: ($$anchor, $$slotProps) => {
											var fragment_7 = root_21();
											Send(first_child(fragment_7), { size: 19 });
											next();
											append($$anchor, fragment_7);
										},
										$$slots: { default: true }
									});
								};
								var alternate_2 = ($$anchor) => {
									var div_14 = root_22();
									bind_this(div_14, ($$value) => set(loginTelegramNode, $$value), () => get(loginTelegramNode));
									append($$anchor, div_14);
								};
								if_block(node_15, ($$render) => {
									if (untrack(() => tg?.initData)) $$render(consequent_7);
									else $$render(alternate_2, -1);
								});
								reset(div_13);
								append($$anchor, div_13);
							};
							if_block(node_11, ($$render) => {
								if (get(authMode) === "email") $$render(consequent_6);
								else $$render(alternate_3, -1);
							});
							var node_17 = sibling(node_11, 2);
							var consequent_8 = ($$anchor) => {
								var div_15 = root_23();
								let classes_4;
								var text_7 = child(div_15, true);
								reset(div_15);
								template_effect(() => {
									classes_4 = set_class(div_15, 1, "status-line", null, classes_4, { error: get(authIsError) });
									set_text(text_7, get(authStatus));
								});
								append($$anchor, div_15);
							};
							if_block(node_17, ($$render) => {
								if (get(authStatus)) $$render(consequent_8);
							});
							template_effect(() => {
								classes_2 = set_class(button_1, 1, "", null, classes_2, { active: get(authMode) === "email" });
								classes_3 = set_class(button_2, 1, "", null, classes_3, { active: get(authMode) === "telegram" });
							});
							event("click", button_1, () => set(authMode, "email"));
							event("click", button_2, openTelegramLogin);
							append($$anchor, fragment_4);
						},
						$$slots: { default: true }
					});
					next(2);
					reset(div_7);
					template_effect(() => set_text(text_6, get(brandTitle)));
					append($$anchor, div_7);
				};
				if_block(node_4, ($$render) => {
					if (get(screen) === "code") $$render(consequent_4);
					else $$render(alternate_4, -1);
				});
				reset(div_3);
				append($$anchor, div_3);
			};
			var alternate_11 = ($$anchor) => {
				var div_16 = root_24();
				var node_18 = child(div_16);
				var consequent_11 = ($$anchor) => {
					var header_1 = root_25();
					var div_17 = child(header_1);
					var div_18 = child(div_17);
					var node_19 = child(div_18);
					var consequent_10 = ($$anchor) => {
						var img_2 = root_26();
						template_effect(() => set_attribute(img_2, "src", untrack(() => CFG.logoUrl)));
						append($$anchor, img_2);
					};
					var alternate_5 = ($$anchor) => {
						var span_4 = root_27();
						var text_8 = child(span_4, true);
						reset(span_4);
						template_effect(() => set_text(text_8, get(brandEmoji)));
						append($$anchor, span_4);
					};
					if_block(node_19, ($$render) => {
						if (untrack(() => CFG.logoUrl)) $$render(consequent_10);
						else $$render(alternate_5, -1);
					});
					reset(div_18);
					var strong_1 = sibling(div_18, 2);
					var text_9 = child(strong_1, true);
					reset(strong_1);
					reset(div_17);
					reset(header_1);
					template_effect(() => set_text(text_9, get(brandTitle)));
					append($$anchor, header_1);
				};
				if_block(node_18, ($$render) => {
					if (get(screen) === "invite" || get(screen) === "settings") $$render(consequent_11);
				});
				var node_20 = sibling(node_18, 2);
				var consequent_13 = ($$anchor) => {
					var main = root_28();
					var div_19 = child(main);
					var div_20 = child(div_19);
					var node_21 = child(div_20);
					var consequent_12 = ($$anchor) => {
						var img_3 = root_29();
						template_effect(() => set_attribute(img_3, "src", untrack(() => CFG.logoUrl)));
						append($$anchor, img_3);
					};
					var alternate_6 = ($$anchor) => {
						var span_5 = root_30();
						var text_10 = child(span_5, true);
						reset(span_5);
						template_effect(() => set_text(text_10, get(brandEmoji)));
						append($$anchor, span_5);
					};
					if_block(node_21, ($$render) => {
						if (untrack(() => CFG.logoUrl)) $$render(consequent_12);
						else $$render(alternate_6, -1);
					});
					reset(div_20);
					var h1_1 = sibling(div_20, 2);
					var text_11 = child(h1_1, true);
					reset(h1_1);
					reset(div_19);
					var div_21 = sibling(div_19, 2);
					var node_22 = child(div_21);
					Card(node_22, {
						class: "status-card",
						children: ($$anchor, $$slotProps) => {
							var div_22 = root_31();
							var node_23 = child(div_22);
							Circle_check(node_23, { size: 23 });
							var div_23 = sibling(node_23, 2);
							var h2 = child(div_23);
							var text_12 = child(h2, true);
							reset(h2);
							var p_1 = sibling(h2, 2);
							var text_13 = child(p_1, true);
							reset(p_1);
							reset(div_23);
							reset(div_22);
							template_effect(() => {
								set_text(text_12, (get(subscription), untrack(() => get(subscription).active ? "Подписка активна" : "Подписка не активна")));
								set_text(text_13, (get(subscription), untrack(() => get(subscription).end_date_text ? `до ${get(subscription).end_date_text}` : get(subscription).remaining_text)));
							});
							append($$anchor, div_22);
						},
						$$slots: { default: true }
					});
					var node_24 = sibling(node_22, 2);
					Card(node_24, {
						children: ($$anchor, $$slotProps) => {
							var fragment_8 = root_32();
							var div_24 = first_child(fragment_8);
							var strong_2 = sibling(child(div_24), 2);
							var text_14 = child(strong_2, true);
							reset(strong_2);
							reset(div_24);
							var div_25 = sibling(div_24, 2);
							var span_6 = child(div_25);
							reset(div_25);
							var div_26 = sibling(div_25, 2);
							var text_15 = child(div_26);
							reset(div_26);
							template_effect(($0, $1, $2) => {
								set_text(text_14, $0);
								set_style(span_6, $1);
								set_text(text_15, `${$2 ?? ""}%`);
							}, [
								() => (get(subscription), untrack(() => trafficLabel(get(subscription)))),
								() => (get(subscription), untrack(() => `width: ${trafficPercent(get(subscription))}%`)),
								() => (get(subscription), untrack(() => trafficPercent(get(subscription))))
							]);
							append($$anchor, fragment_8);
						},
						$$slots: { default: true }
					});
					var div_27 = sibling(node_24, 2);
					var node_25 = child(div_27);
					Button(node_25, {
						class: "wide",
						onclick: openConnectLink,
						children: ($$anchor, $$slotProps) => {
							var fragment_9 = root_33();
							Download(first_child(fragment_9), { size: 18 });
							next();
							append($$anchor, fragment_9);
						},
						$$slots: { default: true }
					});
					var node_27 = sibling(node_25, 2);
					Button(node_27, {
						variant: "secondary",
						class: "wide",
						onclick: () => set(screen, "payment"),
						children: ($$anchor, $$slotProps) => {
							var fragment_10 = root_34();
							Refresh_cw(first_child(fragment_10), { size: 18 });
							next();
							append($$anchor, fragment_10);
						},
						$$slots: { default: true }
					});
					Button(sibling(node_27, 2), {
						variant: "secondary",
						class: "wide",
						onclick: () => set(screen, "change-tariff"),
						children: ($$anchor, $$slotProps) => {
							var fragment_11 = root_35();
							Repeat_2(first_child(fragment_11), { size: 18 });
							next();
							append($$anchor, fragment_11);
						},
						$$slots: { default: true }
					});
					reset(div_27);
					reset(div_21);
					reset(main);
					template_effect(() => set_text(text_11, get(brandTitle)));
					append($$anchor, main);
				};
				var consequent_15 = ($$anchor) => {
					var main_1 = root_36();
					var header_2 = child(main_1);
					Button(child(header_2), {
						variant: "icon",
						size: "icon",
						onclick: goHome,
						"aria-label": "Назад",
						children: ($$anchor, $$slotProps) => {
							Arrow_left($$anchor, { size: 19 });
						},
						$$slots: { default: true }
					});
					next(4);
					reset(header_2);
					var div_28 = sibling(header_2, 2);
					each(div_28, 5, () => demoTariffs, index, ($$anchor, tariff) => {
						var button_3 = root_38();
						let classes_5;
						var span_7 = child(button_3);
						component(child(span_7), () => tariffIcon(get(tariff).id), ($$anchor, $$component) => {
							$$component($$anchor, { size: 25 });
						});
						reset(span_7);
						var span_8 = sibling(span_7, 2);
						var strong_3 = child(span_8);
						var text_16 = child(strong_3, true);
						reset(strong_3);
						var small = sibling(strong_3, 2);
						var text_17 = child(small, true);
						reset(small);
						var em = sibling(small, 2);
						var text_18 = child(em, true);
						reset(em);
						reset(span_8);
						var node_33 = sibling(span_8, 2);
						var consequent_14 = ($$anchor) => {
							Circle_check($$anchor, { size: 22 });
						};
						var alternate_7 = ($$anchor) => {
							Circle($$anchor, { size: 22 });
						};
						if_block(node_33, ($$render) => {
							if (get(selectedTariff), get(tariff), untrack(() => get(selectedTariff) === get(tariff).id)) $$render(consequent_14);
							else $$render(alternate_7, -1);
						});
						reset(button_3);
						template_effect(() => {
							classes_5 = set_class(button_3, 1, "select-card", null, classes_5, { active: get(selectedTariff) === get(tariff).id });
							set_text(text_16, (get(tariff), untrack(() => get(tariff).title)));
							set_text(text_17, (get(tariff), untrack(() => get(tariff).caption)));
							set_text(text_18, (get(tariff), untrack(() => get(tariff).details)));
						});
						event("click", button_3, () => set(selectedTariff, get(tariff).id));
						append($$anchor, button_3);
					});
					reset(div_28);
					Button(sibling(div_28, 2), {
						class: "wide bottom-action",
						onclick: () => showToast("Тарифы пока не подключены"),
						children: ($$anchor, $$slotProps) => {
							next();
							var fragment_15 = root_41();
							Arrow_right(sibling(first_child(fragment_15)), { size: 18 });
							append($$anchor, fragment_15);
						},
						$$slots: { default: true }
					});
					reset(main_1);
					append($$anchor, main_1);
				};
				var consequent_19 = ($$anchor) => {
					var main_2 = root_42();
					var header_3 = child(main_2);
					Button(child(header_3), {
						variant: "icon",
						size: "icon",
						onclick: goHome,
						"aria-label": "Назад",
						children: ($$anchor, $$slotProps) => {
							Arrow_left($$anchor, { size: 19 });
						},
						$$slots: { default: true }
					});
					next(4);
					reset(header_3);
					var div_29 = sibling(header_3, 2);
					each(div_29, 5, () => get(plans), index, ($$anchor, plan) => {
						var button_4 = root_44();
						let classes_6;
						var strong_4 = child(button_4);
						var text_19 = child(strong_4, true);
						reset(strong_4);
						var span_9 = sibling(strong_4, 2);
						var text_20 = child(span_9, true);
						reset(span_9);
						var node_37 = sibling(span_9, 2);
						var consequent_16 = ($$anchor) => {
							var small_1 = root_45();
							var text_21 = child(small_1);
							reset(small_1);
							template_effect(($0) => set_text(text_21, `${$0 ?? ""}/мес`), [() => (get(plan), untrack(() => formatMoney(get(plan).price / get(plan).months, get(plan).currency)))]);
							append($$anchor, small_1);
						};
						if_block(node_37, ($$render) => {
							if (get(plan), untrack(() => get(plan).months > 1)) $$render(consequent_16);
						});
						var node_38 = sibling(node_37, 2);
						var consequent_17 = ($$anchor) => {
							Circle_check($$anchor, { size: 18 });
						};
						if_block(node_38, ($$render) => {
							if (get(selectedPlan), get(plan), untrack(() => get(selectedPlan)?.months === get(plan).months)) $$render(consequent_17);
						});
						reset(button_4);
						template_effect(($0) => {
							classes_6 = set_class(button_4, 1, "period-card", null, classes_6, { active: get(selectedPlan)?.months === get(plan).months });
							set_text(text_19, (get(plan), untrack(() => get(plan).title)));
							set_text(text_20, $0);
						}, [() => (get(plan), untrack(() => formatMoney(get(plan).price, get(plan).currency)))]);
						event("click", button_4, () => set(selectedPlan, get(plan)));
						append($$anchor, button_4);
					});
					reset(div_29);
					var node_39 = sibling(div_29, 2);
					Card(node_39, {
						class: "total-card",
						children: ($$anchor, $$slotProps) => {
							var fragment_18 = root_47();
							var strong_5 = sibling(first_child(fragment_18), 2);
							var text_22 = child(strong_5, true);
							reset(strong_5);
							template_effect(($0) => set_text(text_22, $0), [() => (get(selectedPlan), untrack(() => get(selectedPlan) ? formatMoney(get(selectedPlan).price, get(selectedPlan).currency) : "..."))]);
							append($$anchor, fragment_18);
						},
						$$slots: { default: true }
					});
					var div_30 = sibling(node_39, 2);
					var node_40 = child(div_30);
					var consequent_18 = ($$anchor) => {
						var fragment_19 = comment();
						each(first_child(fragment_19), 1, () => get(methods), index, ($$anchor, method) => {
							const meta = /* @__PURE__ */ derived_safe_equal(() => (get(method), untrack(() => methodMeta(get(method)))));
							var button_5 = root_49();
							let classes_7;
							var node_42 = child(button_5);
							component(node_42, () => get(meta).icon, ($$anchor, $$component) => {
								$$component($$anchor, { size: 19 });
							});
							var span_10 = sibling(node_42, 2);
							var strong_6 = child(span_10);
							var text_23 = child(strong_6, true);
							reset(strong_6);
							var small_2 = sibling(strong_6, 2);
							var text_24 = child(small_2, true);
							reset(small_2);
							reset(span_10);
							reset(button_5);
							template_effect(() => {
								classes_7 = set_class(button_5, 1, "method-card", null, classes_7, { active: get(selectedMethod) === get(method).id });
								set_text(text_23, (deep_read_state(get(meta)), untrack(() => get(meta).title)));
								set_text(text_24, (deep_read_state(get(meta)), untrack(() => get(meta).note)));
							});
							event("click", button_5, () => set(selectedMethod, get(method).id));
							append($$anchor, button_5);
						});
						append($$anchor, fragment_19);
					};
					var alternate_8 = ($$anchor) => {
						Card($$anchor, {
							class: "empty-card",
							children: ($$anchor, $$slotProps) => {
								next();
								append($$anchor, text("Способы оплаты пока не настроены"));
							},
							$$slots: { default: true }
						});
					};
					if_block(node_40, ($$render) => {
						if (get(methods), untrack(() => get(methods).length)) $$render(consequent_18);
						else $$render(alternate_8, -1);
					});
					reset(div_30);
					var node_43 = sibling(div_30, 2);
					{
						let $0 = /* @__PURE__ */ derived_safe_equal(() => (get(methods), get(payBusy), untrack(() => !get(methods).length || get(payBusy))));
						Button(node_43, {
							class: "wide bottom-action",
							onclick: createPayment,
							get disabled() {
								return get($0);
							},
							children: ($$anchor, $$slotProps) => {
								next();
								var fragment_21 = root_52();
								var text_26 = first_child(fragment_21);
								Lock_keyhole(sibling(text_26), { size: 17 });
								template_effect(($0) => set_text(text_26, `Оплатить ${$0 ?? ""} `), [() => (get(selectedPlan), untrack(() => get(selectedPlan) ? formatMoney(get(selectedPlan).price, get(selectedPlan).currency) : ""))]);
								append($$anchor, fragment_21);
							},
							$$slots: { default: true }
						});
					}
					reset(main_2);
					append($$anchor, main_2);
				};
				var consequent_21 = ($$anchor) => {
					var main_3 = root_53();
					var header_4 = child(main_3);
					Button(child(header_4), {
						variant: "icon",
						size: "icon",
						onclick: goHome,
						"aria-label": "Назад",
						children: ($$anchor, $$slotProps) => {
							Arrow_left($$anchor, { size: 19 });
						},
						$$slots: { default: true }
					});
					next(4);
					reset(header_4);
					var div_31 = sibling(header_4, 2);
					each(div_31, 5, () => trafficPackages, index, ($$anchor, pack) => {
						var button_6 = root_55();
						let classes_8;
						var strong_7 = child(button_6);
						var text_27 = child(strong_7);
						reset(strong_7);
						var span_11 = sibling(strong_7, 2);
						var text_28 = child(span_11, true);
						reset(span_11);
						var small_3 = sibling(span_11, 2);
						var text_29 = child(small_3);
						reset(small_3);
						var node_46 = sibling(small_3, 2);
						var consequent_20 = ($$anchor) => {
							Circle_check($$anchor, { size: 18 });
						};
						if_block(node_46, ($$render) => {
							if (get(selectedTrafficPackage), get(pack), untrack(() => get(selectedTrafficPackage).gb === get(pack).gb)) $$render(consequent_20);
						});
						reset(button_6);
						template_effect(($0, $1) => {
							classes_8 = set_class(button_6, 1, "period-card", null, classes_8, { active: get(selectedTrafficPackage).gb === get(pack).gb });
							set_text(text_27, `${(get(pack), untrack(() => get(pack).gb)) ?? ""} ГБ`);
							set_text(text_28, $0);
							set_text(text_29, `${$1 ?? ""}/ГБ`);
						}, [() => (get(pack), untrack(() => formatMoney(get(pack).price))), () => (get(pack), untrack(() => formatMoney(get(pack).price / get(pack).gb)))]);
						event("click", button_6, () => set(selectedTrafficPackage, get(pack)));
						append($$anchor, button_6);
					});
					reset(div_31);
					var node_47 = sibling(div_31, 2);
					Card(node_47, {
						class: "total-card",
						children: ($$anchor, $$slotProps) => {
							var fragment_24 = root_57();
							var strong_8 = sibling(first_child(fragment_24), 2);
							var text_30 = child(strong_8, true);
							reset(strong_8);
							template_effect(($0) => set_text(text_30, $0), [() => (get(selectedTrafficPackage), untrack(() => formatMoney(get(selectedTrafficPackage).price)))]);
							append($$anchor, fragment_24);
						},
						$$slots: { default: true }
					});
					var div_32 = sibling(node_47, 2);
					each(div_32, 5, () => untrack(() => DEV_MOCK.data.payment_methods), index, ($$anchor, method) => {
						const meta = /* @__PURE__ */ derived_safe_equal(() => (get(method), untrack(() => methodMeta(get(method)))));
						var button_7 = root_58();
						var node_48 = child(button_7);
						component(node_48, () => get(meta).icon, ($$anchor, $$component) => {
							$$component($$anchor, { size: 19 });
						});
						var span_12 = sibling(node_48, 2);
						var strong_9 = child(span_12);
						var text_31 = child(strong_9, true);
						reset(strong_9);
						var small_4 = sibling(strong_9, 2);
						var text_32 = child(small_4, true);
						reset(small_4);
						reset(span_12);
						reset(button_7);
						template_effect(() => {
							set_text(text_31, (deep_read_state(get(meta)), untrack(() => get(meta).title)));
							set_text(text_32, (deep_read_state(get(meta)), untrack(() => get(meta).note)));
						});
						append($$anchor, button_7);
					});
					reset(div_32);
					Button(sibling(div_32, 2), {
						class: "wide bottom-action",
						onclick: () => showToast("Пакеты трафика пока не подключены"),
						children: ($$anchor, $$slotProps) => {
							next();
							var fragment_25 = root_59();
							var text_33 = first_child(fragment_25);
							Lock_keyhole(sibling(text_33), { size: 17 });
							template_effect(($0) => set_text(text_33, `Оплатить ${$0 ?? ""} `), [() => (get(selectedTrafficPackage), untrack(() => formatMoney(get(selectedTrafficPackage).price)))]);
							append($$anchor, fragment_25);
						},
						$$slots: { default: true }
					});
					reset(main_3);
					append($$anchor, main_3);
				};
				var consequent_23 = ($$anchor) => {
					var main_4 = root_60();
					var header_5 = child(main_4);
					Button(child(header_5), {
						variant: "icon",
						size: "icon",
						onclick: goHome,
						"aria-label": "Назад",
						children: ($$anchor, $$slotProps) => {
							Arrow_left($$anchor, { size: 19 });
						},
						$$slots: { default: true }
					});
					next(4);
					reset(header_5);
					var div_33 = sibling(header_5, 2);
					each(div_33, 5, () => changeTariffs, index, ($$anchor, tariff) => {
						var button_8 = root_62();
						let classes_9;
						var span_13 = child(button_8);
						var strong_10 = child(span_13);
						var text_34 = child(strong_10, true);
						reset(strong_10);
						var small_5 = sibling(strong_10, 2);
						var text_35 = child(small_5, true);
						reset(small_5);
						reset(span_13);
						var em_1 = sibling(span_13, 2);
						var text_36 = child(em_1, true);
						reset(em_1);
						var node_52 = sibling(em_1, 2);
						var consequent_22 = ($$anchor) => {
							Circle_check($$anchor, { size: 20 });
						};
						var alternate_9 = ($$anchor) => {
							Circle($$anchor, { size: 20 });
						};
						if_block(node_52, ($$render) => {
							if (get(selectedChangeTariff), get(tariff), untrack(() => get(selectedChangeTariff) === get(tariff).id)) $$render(consequent_22);
							else $$render(alternate_9, -1);
						});
						reset(button_8);
						template_effect(() => {
							classes_9 = set_class(button_8, 1, "select-card", null, classes_9, { active: get(selectedChangeTariff) === get(tariff).id });
							set_text(text_34, (get(tariff), untrack(() => get(tariff).title)));
							set_text(text_35, (get(tariff), untrack(() => get(tariff).caption)));
							set_text(text_36, (get(tariff), untrack(() => get(tariff).recalculation)));
						});
						event("click", button_8, () => set(selectedChangeTariff, get(tariff).id));
						append($$anchor, button_8);
					});
					reset(div_33);
					Button(sibling(div_33, 2), {
						class: "wide bottom-action",
						onclick: () => get(selectedChangeTariff) === "traffic" ? set(confirmTariffOpen, true) : showToast("Оплата смены тарифа пока не подключена"),
						children: ($$anchor, $$slotProps) => {
							next();
							var fragment_29 = root_65();
							Arrow_right(sibling(first_child(fragment_29)), { size: 18 });
							append($$anchor, fragment_29);
						},
						$$slots: { default: true }
					});
					reset(main_4);
					append($$anchor, main_4);
				};
				var consequent_25 = ($$anchor) => {
					var main_5 = root_66();
					var node_55 = child(main_5);
					Card(node_55, {
						children: ($$anchor, $$slotProps) => {
							var fragment_30 = root_67();
							var div_34 = sibling(first_child(fragment_30), 2);
							var code_1 = child(div_34);
							var text_37 = child(code_1, true);
							reset(code_1);
							Button(sibling(code_1, 2), {
								onclick: () => copyText(get(referral).webapp_link || get(referral).bot_link, "Ссылка скопирована"),
								children: ($$anchor, $$slotProps) => {
									next();
									var fragment_31 = root_68();
									Copy(sibling(first_child(fragment_31)), { size: 17 });
									append($$anchor, fragment_31);
								},
								$$slots: { default: true }
							});
							reset(div_34);
							template_effect(() => set_text(text_37, (get(referral), untrack(() => get(referral).webapp_link || get(referral).bot_link || "Ссылка пока недоступна"))));
							append($$anchor, fragment_30);
						},
						$$slots: { default: true }
					});
					var node_58 = sibling(node_55, 2);
					Card(node_58, {
						class: "bonus-card",
						children: ($$anchor, $$slotProps) => {
							var fragment_32 = root_69();
							Gift(first_child(fragment_32), { size: 42 });
							next(2);
							append($$anchor, fragment_32);
						},
						$$slots: { default: true }
					});
					Card(sibling(node_58, 2), {
						children: ($$anchor, $$slotProps) => {
							var fragment_33 = root_70();
							var div_35 = sibling(first_child(fragment_33), 2);
							var node_61 = child(div_35);
							Input(node_61, {
								placeholder: "PROMO2026",
								get value() {
									return get(promoCode);
								},
								set value($$value) {
									set(promoCode, $$value);
								},
								$$legacy: true
							});
							Button(sibling(node_61, 2), {
								variant: "outline",
								onclick: applyPromo,
								get disabled() {
									return get(promoBusy);
								},
								children: ($$anchor, $$slotProps) => {
									var fragment_34 = root_71();
									Ticket(first_child(fragment_34), { size: 17 });
									next();
									append($$anchor, fragment_34);
								},
								$$slots: { default: true }
							});
							reset(div_35);
							var node_64 = sibling(div_35, 2);
							var consequent_24 = ($$anchor) => {
								var p_2 = root_72();
								let classes_10;
								var text_38 = child(p_2, true);
								reset(p_2);
								template_effect(() => {
									classes_10 = set_class(p_2, 1, "status-line", null, classes_10, { error: get(promoIsError) });
									set_text(text_38, get(promoStatus));
								});
								append($$anchor, p_2);
							};
							if_block(node_64, ($$render) => {
								if (get(promoStatus)) $$render(consequent_24);
							});
							append($$anchor, fragment_33);
						},
						$$slots: { default: true }
					});
					reset(main_5);
					append($$anchor, main_5);
				};
				var consequent_27 = ($$anchor) => {
					var main_6 = root_73();
					var node_65 = child(main_6);
					Card(node_65, {
						class: "settings-profile",
						children: ($$anchor, $$slotProps) => {
							var fragment_35 = root_74();
							var div_36 = first_child(fragment_35);
							var node_66 = child(div_36);
							var consequent_26 = ($$anchor) => {
								var img_4 = root_75();
								template_effect(() => set_attribute(img_4, "src", get(profileAvatarUrl)));
								append($$anchor, img_4);
							};
							var alternate_10 = ($$anchor) => {
								User_round($$anchor, { size: 30 });
							};
							if_block(node_66, ($$render) => {
								if (get(profileAvatarUrl)) $$render(consequent_26);
								else $$render(alternate_10, -1);
							});
							reset(div_36);
							var div_37 = sibling(div_36, 2);
							var strong_11 = child(div_37);
							var text_39 = child(strong_11, true);
							reset(strong_11);
							var small_6 = sibling(strong_11, 2);
							var text_40 = child(small_6, true);
							reset(small_6);
							var small_7 = sibling(small_6, 2);
							var text_41 = child(small_7, true);
							reset(small_7);
							reset(div_37);
							template_effect(() => {
								set_text(text_39, get(telegramProfileName));
								set_text(text_40, get(profileEmail));
								set_text(text_41, get(profileTelegramId));
							});
							append($$anchor, fragment_35);
						},
						$$slots: { default: true }
					});
					var div_38 = sibling(node_65, 2);
					var button_9 = child(div_38);
					var node_67 = child(button_9);
					Earth(node_67, { size: 21 });
					var span_14 = sibling(node_67, 2);
					var small_8 = sibling(child(span_14));
					var text_42 = child(small_8, true);
					reset(small_8);
					reset(span_14);
					Arrow_right(sibling(span_14, 2), { size: 17 });
					reset(button_9);
					var button_10 = sibling(button_9, 2);
					var node_69 = child(button_10);
					Send(node_69, { size: 21 });
					var span_15 = sibling(node_69, 2);
					var small_9 = sibling(child(span_15));
					var text_43 = child(small_9, true);
					reset(small_9);
					reset(span_15);
					Arrow_right(sibling(span_15, 2), { size: 17 });
					reset(button_10);
					var button_11 = sibling(button_10, 2);
					var node_71 = child(button_11);
					Mail(node_71, { size: 21 });
					var span_16 = sibling(node_71, 2);
					var small_10 = sibling(child(span_16));
					var text_44 = child(small_10, true);
					reset(small_10);
					reset(span_16);
					Arrow_right(sibling(span_16, 2), { size: 17 });
					reset(button_11);
					var button_12 = sibling(button_11, 2);
					var node_73 = child(button_12);
					User_round(node_73, { size: 21 });
					Arrow_right(sibling(node_73, 4), { size: 17 });
					reset(button_12);
					reset(div_38);
					reset(main_6);
					template_effect(() => {
						set_text(text_42, get(userLanguage));
						set_text(text_43, (get(user), untrack(() => get(user).telegram_linked ? `@${get(user).username || "username"}` : "Не привязан")));
						set_text(text_44, (get(user), untrack(() => get(user).email || "Не привязана")));
					});
					event("click", button_12, logout);
					append($$anchor, main_6);
				};
				if_block(node_20, ($$render) => {
					if (get(screen) === "home") $$render(consequent_13);
					else if (get(screen) === "tariff-select") $$render(consequent_15, 1);
					else if (get(screen) === "payment") $$render(consequent_19, 2);
					else if (get(screen) === "traffic-payment") $$render(consequent_21, 3);
					else if (get(screen) === "change-tariff") $$render(consequent_23, 4);
					else if (get(screen) === "invite") $$render(consequent_25, 5);
					else if (get(screen) === "settings") $$render(consequent_27, 6);
				});
				var node_75 = sibling(node_20, 2);
				var consequent_28 = ($$anchor) => {
					var nav = root_77();
					var button_13 = child(nav);
					let classes_11;
					House(child(button_13), { size: 21 });
					next(2);
					reset(button_13);
					var button_14 = sibling(button_13, 2);
					let classes_12;
					Gift(child(button_14), { size: 21 });
					next(2);
					reset(button_14);
					var button_15 = sibling(button_14, 2);
					let classes_13;
					Settings(child(button_15), { size: 21 });
					next(2);
					reset(button_15);
					reset(nav);
					template_effect(() => {
						classes_11 = set_class(button_13, 1, "", null, classes_11, { active: get(activeTab) === "home" });
						classes_12 = set_class(button_14, 1, "", null, classes_12, { active: get(activeTab) === "invite" });
						classes_13 = set_class(button_15, 1, "", null, classes_13, { active: get(activeTab) === "settings" });
					});
					event("click", button_13, goHome);
					event("click", button_14, goInvite);
					event("click", button_15, goSettings);
					append($$anchor, nav);
				};
				if_block(node_75, ($$render) => {
					if (get(screen) === "home" || get(screen) === "invite" || get(screen) === "settings") $$render(consequent_28);
				});
				reset(div_16);
				append($$anchor, div_16);
			};
			if_block(node_2, ($$render) => {
				if (get(mode) === "loading") $$render(consequent_2);
				else if (get(mode) === "login") $$render(consequent_9, 1);
				else $$render(alternate_11, -1);
			});
			var node_79 = sibling(node_2, 2);
			Dialog(node_79, {
				get open() {
					return get(confirmTariffOpen);
				},
				title: "Сменить тариф без доплаты?",
				description: "Остаток 12 дней будет пересчитан по новому тарифу.",
				onclose: () => set(confirmTariffOpen, false),
				children: ($$anchor, $$slotProps) => {
					var div_39 = root_78();
					var node_80 = child(div_39);
					Button(node_80, {
						onclick: () => {
							set(confirmTariffOpen, false);
							showToast("Смена тарифа пока не подключена");
						},
						children: ($$anchor, $$slotProps) => {
							next();
							append($$anchor, text("Да, сменить"));
						},
						$$slots: { default: true }
					});
					Button(sibling(node_80, 2), {
						variant: "secondary",
						onclick: () => set(confirmTariffOpen, false),
						children: ($$anchor, $$slotProps) => {
							next();
							append($$anchor, text("Отмена"));
						},
						$$slots: { default: true }
					});
					reset(div_39);
					append($$anchor, div_39);
				},
				$$slots: { default: true }
			});
			var node_82 = sibling(node_79, 2);
			var consequent_29 = ($$anchor) => {
				var div_40 = root_81();
				var text_47 = child(div_40, true);
				reset(div_40);
				template_effect(() => set_text(text_47, get(toastText)));
				append($$anchor, div_40);
			};
			if_block(node_82, ($$render) => {
				if (get(toastText)) $$render(consequent_29);
			});
			reset(div);
			template_effect(() => set_style(div, `--accent: ${get(accent)};`));
			append($$anchor, div);
		};
		if_block(node_1, ($$render) => {
			if (isPreviewBoard) $$render(consequent);
			else $$render(alternate_12, -1);
		});
		append($$anchor, fragment);
		pop();
	}
	//#endregion
	//#region bot/app/web/frontend/src/main.js
	var target = document.getElementById("app");
	if (target) mount(App, { target });
	//#endregion
})();
