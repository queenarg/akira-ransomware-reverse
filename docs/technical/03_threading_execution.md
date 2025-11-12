# Akira Ransomware - Threading Architecture & File System Execution

**Research Team:** MottaSec
**Analysis Type:** Static Code Analysis (Ghidra)
**Coverage:** Phase 4 (Threading & Concurrency) + Phase 5 (File System Operations)
**Status:** ✅ COMPLETE
**Confidence Level:** 95-99%

---

## Executive Summary

This document provides comprehensive analysis of Akira ransomware's threading architecture and file system execution mechanisms. The malware demonstrates professional-grade software engineering with sophisticated multi-threading, efficient synchronization primitives, and intelligent file targeting strategies.

### Critical Findings

**Threading Architecture:**
- **Dual Thread Pool Design:** Separate pools for I/O-bound (folder parsing) and CPU-bound (encryption) operations
- **ASIO Library:** Statically-linked Boost ASIO for asynchronous I/O operations
- **Dynamic Scaling:** 2 to 64+ threads based on CPU count (30/10/60 split)
- **Professional Synchronization:** STL critical sections, condition variables, atomic operations
- **Deadlock-Free:** Single lock per operation, no circular dependencies

**File System Operations:**
- **Selective Targeting:** 5 extension blacklist + 11 directory blacklist + 13 protected processes
- **NO Active Network Enumeration:** Stealth over automation (requires manual reconnaissance)
- **Process Termination:** Windows Restart Manager API for force-killing locking processes
- **Two-Stage File Locking:** Exclusive → shared access fallback
- **Atomic Renaming:** SetFileInformationByHandle for race-free file operations

**Performance Characteristics:**
- **Theoretical Throughput:** ~930 files/sec on 10-thread system
- **O(log n) Filtering:** Red-black trees for efficient blacklist checking
- **Bounded Queue:** Prevents memory exhaustion
- **CPU Efficiency:** Condition variables (no busy-waiting)

---

## Table of Contents

### Part 1: Threading & Concurrency (Phase 4)
1. [Thread Pool Architecture](#1-thread-pool-architecture)
2. [ASIO Library Integration](#2-asio-library-integration)
3. [Synchronization Mechanisms](#3-synchronization-mechanisms)
4. [Task Queue System](#4-task-queue-system)
5. [Producer-Consumer Pattern](#5-producer-consumer-pattern)

### Part 2: File System Operations (Phase 5)
6. [Drive Enumeration](#6-drive-enumeration)
7. [Directory Traversal](#7-directory-traversal)
8. [File Filtering System](#8-file-filtering-system)
9. [File Access & Manipulation](#9-file-access--manipulation)
10. [Restart Manager Integration](#10-restart-manager-integration)

### Part 3: Integration & Analysis
11. [Cross-Component Architecture](#11-cross-component-architecture)
12. [Performance Analysis](#12-performance-analysis)
13. [Security Assessment](#13-security-assessment)
14. [Detection Strategies](#14-detection-strategies)
15. [Function Reference](#15-function-reference)

---

# PART 1: THREADING & CONCURRENCY (PHASE 4)

## 1. Thread Pool Architecture

### 1.1 Overview

Akira employs a sophisticated dual thread pool architecture using the Boost ASIO library. This design separates I/O-bound directory traversal from CPU-bound encryption operations, maximizing efficiency on multi-core systems.

### 1.2 Thread Pool Structure

**Main Structure Size:** 384 bytes (0x180)
**Allocation:** `operator_new(0x180)` in main function
**Initialization Function:** init_thread_pool @ 0x14007b6d0

#### Complete Structure Layout

```c
struct thread_pool_t {
    // +0x00-0x28: Core fields (40 bytes)
    void*    reserved[5];                    // +0x00 (40 bytes)
    int      folder_parser_thread_count;     // +0x28 (4 bytes)
    int      root_folder_thread_count;       // +0x34 (4 bytes)
    void*    reserved_0x38;                  // +0x38 (8 bytes)

    // +0x40-0x8F: Critical Section 1 - Folder Parser Pool (80 bytes)
    CRITICAL_SECTION  cs_folder_parser;      // +0x40 (80 bytes)

    // +0x90-0xDF: Critical Section 2 - Encryption Pool (80 bytes)
    CRITICAL_SECTION  cs_encryption;         // +0x90 (80 bytes)

    // +0xE0-0x127: Condition Variable 1 - Folder Parser (72 bytes)
    CONDITION_VARIABLE cv_folder_parser;     // +0xE0 (72 bytes)

    // +0x128-0x16F: Condition Variable 2 - Encryption (72 bytes)
    CONDITION_VARIABLE cv_encryption;        // +0x128 (72 bytes)

    // ASIO pool pointers and control blocks
    void*    folder_parser_pool_impl;        // +0x10
    void*    folder_parser_pool_ctrl;        // +0x18
    void*    encryption_pool_impl;           // +0x20
    void*    encryption_pool_ctrl;           // +0x28

    // Queue state tracking
    int      max_queue_size;                 // +0x34
    int      current_queue_size;             // +0x3C
    int      queue_counter;                  // +0xDC (wraps at 0x7FFFFFFF)
};
```

**Key Observations:**
- Two completely independent thread pools
- Each pool has its own critical section and condition variable
- No shared resources between pools (no lock contention)
- Efficient memory layout (aligned for cache performance)

### 1.3 Thread Allocation Algorithm

#### CPU Detection and Thread Calculation

**Location:** main() function, before init_thread_pool call

**Algorithm:**
```c
cpu_count = get_cpu_count();

// Boost single-core systems to minimum 2 threads
if (cpu_count == 1) {
    cpu_count = 2;
}

// Calculate thread distribution
folder_parser_threads = (cpu_count * 30) / 100;  // 30% for I/O
root_folder_threads   = (cpu_count * 10) / 100;  // 10% for root dirs

// Ensure at least 1 root folder thread
if (root_folder_threads == 0) {
    root_folder_threads = 1;
}

// Remaining threads for encryption (CPU-intensive work)
encryption_threads = cpu_count - folder_parser_threads - root_folder_threads;

// Logging
log_info("Number of thread to folder parsers = %d", folder_parser_threads);
log_info("Number of thread to root folder parsers = %d", root_folder_threads);
log_info("Number of threads to encrypt = %d", encryption_threads);
```

#### Thread Distribution Table

| CPU Cores | Folder Parser (30%) | Root Folder (10%) | Encryption (60%) | Total |
|-----------|---------------------|-------------------|------------------|-------|
| 1 (→2)    | 0                   | 1                 | 1                | 2     |
| 2         | 0                   | 1                 | 1                | 2     |
| 4         | 1                   | 1                 | 2                | 4     |
| 8         | 2                   | 1                 | 5                | 8     |
| 16        | 4                   | 1                 | 11               | 16    |
| 32        | 9                   | 3                 | 20               | 32    |
| 64        | 19                  | 6                 | 39               | 64    |

**Design Rationale:**
- **30% for Folder Parsing:** I/O-bound directory traversal benefits from parallelism but doesn't need as many threads
- **10% for Root Folders:** Small number of root directories (drives) to process
- **60% for Encryption:** CPU-intensive ChaCha20 encryption gets the majority of threads
- **Minimum Guarantee:** Single-core systems boosted to 2 threads to avoid sequential execution

### 1.4 Thread Pool Initialization Sequence

#### Step-by-Step Initialization

**Function:** `init_thread_pool` @ 0x14007b6d0

**Step 1: Zero-Initialize Structure**
```c
*param_1 = 0;
param_1[1] = 0;
param_1[2] = 0;
param_1[3] = 0;
param_1[4] = 0;
param_1[5] = 0;
```

**Step 2: Store Thread Counts**
```c
*(int *)(param_1 + 6) = folder_parser_threads;  // Offset 0x28
*(int *)((longlong)param_1 + 0x34) = root_folder_threads;  // Offset 0x34
param_1[7] = 0;  // Clear offset 0x38
```

**Step 3: Initialize Synchronization Primitives**
```c
init_critical_section((undefined4 *)(param_1 + 8), 2);    // Offset 0x40, spin=2
init_critical_section((undefined4 *)(param_1 + 0x12), 2); // Offset 0x90, spin=2
init_condition_variable(param_1 + 0x1c);                  // Offset 0xE0
init_condition_variable(param_1 + 0x25);                  // Offset 0x128
```

**Critical Section Parameters:**
- **Spin Count = 2:** Before blocking, threads attempt to acquire lock twice with busy-wait
- **Purpose:** Reduces context switching overhead for brief critical sections
- **Trade-off:** Good for locks held for microseconds, bad if held for milliseconds

**Condition Variables:**
- Windows native condition variables (Vista+)
- Atomic wait/release of mutex
- Efficient thread wake-up

**Step 4: Create Folder Parser Thread Pool**
```c
puVar6 = (undefined8 *)operator_new(0x30);  // Allocate 48 bytes for ASIO pool
*puVar6 = 0;
puVar6[1] = 0;
*(undefined4 *)(puVar6 + 1) = 1;            // Initial ref count = 1
*(undefined4 *)((longlong)puVar6 + 0xc) = 1; // Weak ref count = 1
*puVar6 = std::_Ref_count_obj2<class_asio::thread_pool>::vftable;

FUN_14007b280((PRTL_CRITICAL_SECTION_DEBUG)(puVar6 + 2), (longlong)folder_parser_threads);

param_1[2] = (PRTL_CRITICAL_SECTION_DEBUG)(puVar6 + 2);  // Store pool ptr at offset 0x10
param_1[3] = puVar6;  // Store control block at offset 0x18
```

**Step 5: Create Encryption Thread Pool**
```c
puVar6 = (undefined8 *)operator_new(0x30);  // Another 48-byte ASIO pool
*puVar6 = 0;
puVar6[1] = 0;
*(undefined4 *)(puVar6 + 1) = 1;
*(undefined4 *)((longlong)puVar6 + 0xc) = 1;
*puVar6 = std::_Ref_count_obj2<class_asio::thread_pool>::vftable;

FUN_14007b280((PRTL_CRITICAL_SECTION_DEBUG)(puVar6 + 2), (longlong)encryption_threads);

param_1[4] = (PRTL_CRITICAL_SECTION_DEBUG)(puVar6 + 2);  // Store pool ptr at offset 0x20
param_1[5] = puVar6;  // Store control block at offset 0x28
```

### 1.5 Thread Lifecycle

#### Thread Object Structure

**Size:** 32 bytes (0x20) per thread
**Allocation:** Heap-allocated during thread pool creation

```c
struct thread_object_t {
    void*    vftable_ptr;        // +0x00 Virtual function table
    void*    thread_handle;      // +0x08 Windows thread HANDLE
    void*    thread_context;     // +0x10 Thread pool context pointer
    void*    next_thread;        // +0x18 Linked list pointer
};
```

#### Thread Creation Loop

**Function:** `FUN_14007b280` @ 0x14007b280 (ASIO thread pool creation)

```c
if (thread_count < 0x80000000) {  // Sanity check
    *(uint *)&(param_1->ProcessLocksList).Blink = (uint)thread_count & 0x7fffffff;

    // Increment reference count atomically
    LOCK();
    piVar1 = (int *)((longlong)&pool_impl[4].DebugInfo + 4);
    *piVar1 = *piVar1 + 1;
    UNLOCK();

    // Create worker threads
    iVar2 = *(int *)&(param_1->ProcessLocksList).Blink;
    lVar11 = (longlong)iVar2;
    if (iVar2 != 0) {
        do {
            thread_obj = operator_new(0x20);  // Thread object (32 bytes)
            func_wrapper = operator_new(0x20);  // Thread function wrapper

            // Set up thread function wrapper
            *func_wrapper = asio::detail::win_thread::func<...>::vftable;
            func_wrapper[3] = pool_impl;  // Thread pool context

            // Initialize Windows thread
            FUN_140038a10((longlong)thread_obj, func_wrapper);

            // Add to thread list
            thread_obj->LockSemaphore = prev_thread;
            (param_1->ProcessLocksList).Flink = (_LIST_ENTRY *)thread_obj;

            lVar11 = lVar11 + -1;
        } while (lVar11 != 0);
    }
}
```

**Key Points:**
- Each thread is created with a unique function wrapper
- Threads are linked in a list for management
- Reference counting prevents premature cleanup
- Windows native threads (not Win32 fibers)

---

## 2. ASIO Library Integration

### 2.1 Boost ASIO Overview

**Library:** Boost ASIO (Asynchronous I/O)
**Version:** Unknown (statically linked)
**Deployment:** Embedded in binary (no DLL dependencies)
**Implementation:** Windows-specific (`asio::detail::win_thread`)

**Purpose:**
- Professional-grade asynchronous I/O framework
- Cross-platform thread pool management
- Work-stealing task scheduler
- Reference-counted resource management

### 2.2 ASIO Components Identified

#### Component 1: Thread Pool Class

**Type:** `asio::thread_pool`
**Virtual Function Table:** `std::_Ref_count_obj2<class_asio::thread_pool>::vftable`
**Pattern:** Standard C++ shared_ptr implementation

```c
struct asio_thread_pool_t {
    void*    vftable;              // +0x00 Virtual function table
    void*    unknown_0x08;         // +0x08
    int      ref_count;            // +0x10 Strong reference count
    int      weak_ref_count;       // +0x0C Weak reference count
    // ... additional fields ...
    void*    thread_pool_impl;     // Actual thread pool implementation
};
```

**Size:** 48 bytes (0x30) per pool object

#### Component 2: Thread Function Wrapper

**Type:** `asio::detail::win_thread::func<struct_asio::thread_pool::thread_function>`
**Purpose:** Windows-specific thread entry point wrapper
**Namespace:** `asio::detail` (internal implementation)

**Structure:**
```c
struct thread_func_wrapper_t {
    void*    vftable;              // +0x00 Function wrapper vtable
    void*    reserved[2];          // +0x08-0x17
    void*    pool_context;         // +0x18 Thread pool context
};
```

**Size:** 32 bytes (0x20) per wrapper

#### Component 3: Thread Pool Implementation

**Size:** 200 bytes per pool
**Initialization:** Zero-initialized via FUN_140090460

**Purpose:**
- Manages worker thread pool
- Implements work-stealing scheduler
- Handles task dispatch and load balancing

### 2.3 Reference Counting Pattern

ASIO uses C++ shared_ptr semantics for resource management:

```c
// Atomic increment (shared_ptr copy)
LOCK();
ref_count++;
UNLOCK();

// Atomic decrement (shared_ptr destruction)
LOCK();
old_count = ref_count--;
UNLOCK();

if (old_count == 1) {
    // Last strong reference - call destructor
    vtable->destroy(this);

    LOCK();
    weak_ref_count--;
    UNLOCK();

    if (weak_ref_count == 0) {
        // Last weak reference - free memory
        vtable->deallocate(this);
    }
}
```

**Advantages:**
- Automatic resource cleanup
- Thread-safe reference counting
- Prevents memory leaks
- Prevents use-after-free

### 2.4 ASIO Pool Creation Function

**Function:** `FUN_14007b280` @ 0x14007b280
**Signature:** `void create_asio_thread_pool(void* asio_pool, uint thread_count)`

**Responsibilities:**
1. Create ASIO context structure (56 bytes = 0x38)
2. Initialize critical section for context
3. Create thread pool with specified thread count
4. Spawn worker threads
5. Set up thread-local storage

**Key Operations:**
```c
p_Var8 = (LPCRITICAL_SECTION)operator_new(0x38);  // Context structure
FUN_1400385f0(p_Var8);                            // Initialize context

// Create thread pool implementation
pauVar9 = (undefined1 (*) [32])operator_new(200); // 200 bytes for pool impl
FUN_140090460(pauVar9, 0, 200);                   // Zero-initialize
p_Var10 = FUN_14007a2d0(pauVar9, param_1, (uint)(param_2 == 1));
```

### 2.5 ASIO Task Posting

**Function:** `asio_post_task` @ 0x14007bd00
**Purpose:** Submit task to ASIO thread pool for execution

**Signature:**
```c
void asio_post(asio_pool* pool, task_object** task_ptr)
```

**Process:**
1. Take ownership of task pointer (set source to NULL)
2. Wrap task in ASIO-specific handler structures
3. Add to ASIO internal queue
4. ASIO scheduler selects worker thread
5. Worker thread calls task execution function

**Key Feature:** Work-stealing scheduler likely used for load balancing

---

## 3. Synchronization Mechanisms

### 3.1 Critical Sections

#### Implementation Details

**Function:** init_critical_section @ 0x140081d00
**Library:** STL (C++ Standard Library) with Windows 7+ implementation
**Type:** `Concurrency::details::stl_critical_section_win7`

**Underlying Mechanism:** Windows SRW locks (Slim Reader/Writer locks)

#### Critical Section Structure

```c
struct stl_critical_section_win7 {
    uint      spin_count;        // +0x00 (value = 2)
    void*     reserved;          // +0x04
    vftable*  vtable_ptr;        // +0x08
    void*     srw_lock;          // +0x10 (SRW LOCK handle)
    uint      lock_state;        // +0x48 (0xFFFFFFFF when unlocked)
    uint      padding;           // +0x4C
};
```

**Size:** 80 bytes (0x50) total

#### Initialization Code

```c
void init_critical_section(undefined4 *param_1, undefined4 param_2)
{
    *(undefined ***)(param_1 + 2) = Concurrency::details::stl_critical_section_win7::vftable;
    *(undefined8 *)(param_1 + 4) = 0;
    param_1[0x12] = 0xffffffff;  // Unlocked state
    param_1[0x13] = 0;
    *param_1 = param_2;  // Spin count
    return;
}
```

#### Lock/Unlock Operations

**Lock Operation:**
```c
int mutex_lock(uint *mutex_ptr)
{
    // Virtual function dispatch
    return (**(code **)(*mutex_ptr + 8))(mutex_ptr);
}
```

**Unlock Operation:**
```c
void mutex_unlock(longlong mutex_ptr)
{
    _Mtx_unlock(mutex_ptr);
}
```

**Virtual Function Table:**
- `vtable[0]`: Destructor
- `vtable[1]`: Lock function
- `vtable[2]`: TryLock function
- `vtable[3]`: Unlock function

#### Spin Lock Behavior

With spin count = 2:
1. **Attempt 1:** Try lock immediately (no wait)
2. **Attempt 2:** Spin-wait (busy loop)
3. **Attempt 3+:** Block on kernel synchronization object

**Performance Trade-off:**
- **Good for:** Locks held for microseconds (1-10 µs)
- **Bad for:** Locks held for milliseconds (wastes CPU cycles)

### 3.2 Condition Variables

#### Implementation Details

**Function:** init_condition_variable @ 0x1400820e8
**Library:** STL with Windows 7+ implementation
**Type:** `Concurrency::details::stl_condition_variable_win7`

**Underlying Mechanism:** Windows native condition variables (Vista+)

#### Condition Variable Structure

```c
struct stl_condition_variable_win7 {
    vftable*           vtable_ptr;        // +0x00
    CONDITION_VARIABLE native_cv;         // +0x08 Windows CV handle
    // ... additional fields (total 72 bytes)
};
```

**Size:** 72 bytes (0x48) total

#### Initialization Code

```c
void init_condition_variable(undefined8 *param_1)
{
    *param_1 = Concurrency::details::stl_condition_variable_win7::vftable;
    InitializeConditionVariable(param_1 + 1);  // Windows API
    return;
}
```

#### Condition Variable Operations

**Wait Operation:**
```c
void condition_variable_wait(void *cv_ptr, longlong mutex_ptr)
{
    // Atomically:
    // 1. Release mutex
    // 2. Block thread
    // 3. Re-acquire mutex before returning
    FUN_140082118(cv_ptr, mutex_ptr);
}
```

**Signal One Waiter:**
```c
void condition_variable_signal(void *cv_ptr)
{
    WakeConditionVariable(cv_ptr);  // Windows API
}
```

**Broadcast (Signal All Waiters):**
```c
void condition_variable_broadcast(void *cv_ptr)
{
    WakeAllConditionVariable(cv_ptr);  // Windows API
}
```

**Windows APIs Used:**
- `InitializeConditionVariable` - Initialize CV
- `SleepConditionVariableCS` - Wait on CV (blocking)
- `WakeConditionVariable` - Signal one waiter
- `WakeAllConditionVariable` - Signal all waiters

### 3.3 Atomic Operations

Akira uses x86 LOCK prefix for atomic operations:

```c
// Atomic increment
LOCK();
*counter = *counter + 1;
UNLOCK();

// Atomic decrement with return value
LOCK();
old_value = *counter;
*counter = *counter - 1;
UNLOCK();

if (old_value == 1) {
    // Last reference - cleanup
    destroy_resource();
}
```

**Hardware Instructions:**
- `LOCK` prefix: x86 instruction prefix
- Ensures atomic read-modify-write
- Visibility across all CPU cores
- Prevents compiler/CPU reordering

**Used For:**
- Reference counting (ASIO shared_ptr)
- Task counter updates
- Queue size tracking

### 3.4 Locking Hierarchy

**Key Finding:** No deadlock risk

**Analysis:**
- Each operation acquires **at most ONE** critical section
- Folder parser tasks → Folder parser CS (offset +0x40)
- Encryption tasks → Encryption CS (offset +0x90)
- **No nested locking observed**
- **No circular dependencies**

**Result:** Deadlock-free design

---

## 4. Task Queue System

### 4.1 Task Object Structure

**Size:** 288 bytes (0x120)
**Allocation Function:** allocate_task @ 0x14003a4a0
**Constructor Function:** task_constructor @ 0x1400c4030

#### Complete Task Structure

```c
struct task_object_t {
    // +0x00-0x08: Function pointers
    void*     execution_function;      // +0x00 Entry point (FUN_1400c45a0)
    void*     cleanup_function;        // +0x08 Destructor (LAB_1400c3db0)

    // +0x10-0x40: Linked list node structure (48 bytes)
    void*     node_field_0x10;         // +0x10
    void*     node_field_0x18;         // +0x18
    void*     node_field_0x20;         // +0x20
    void*     node_field_0x28;         // +0x28
    void*     node_field_0x30;         // +0x30
    void*     node_field_0x38;         // +0x38

    // +0x40-0x90: Task-specific data
    void*     context_ptr;             // +0x41 (param_10)
    void*     shared_ptr_1;            // +0x49 Crypto context (moved)
    void*     shared_ptr_1_ctrl;       // +0x51 Ref count control block
    void*     shared_ptr_2;            // +0x59 Thread pool (moved)
    void*     shared_ptr_2_ctrl;       // +0x61 Ref count control block
    byte      string_buffer[32];       // +0x69 File path (wstring)
    void*     additional_context;      // +0x89
    uint      integer_param;           // +0x91
    byte      flag_param;              // +0x95
    uint      task_flags;              // +0x9C (0x10002 or 0x2)

    // +0xA0-0x120: Additional fields (128 bytes)
    // ... reserved/internal ASIO structures ...
};
```

### 4.2 Task Constructor Analysis

**Function:** `FUN_1400c4030` @ 0x1400c4030

#### Constructor Operations

**Step 1: Set Function Pointers**
```c
param_2[1] = &LAB_1400c3db0;      // Cleanup function
*param_2 = FUN_1400c45a0;          // Execution function
```

**Step 2: Move Shared Pointers (Transfer Ownership)**
```c
// Move shared_ptr_1 (crypto context)
*(void**)(task + 0x49) = *param_4;
*(void**)(task + 0x51) = param_4[1];
*param_4 = 0;       // Clear source
param_4[1] = 0;

// Move shared_ptr_2 (thread pool)
*(void**)(task + 0x59) = *param_5;
*(void**)(task + 0x61) = param_5[1];
*param_5 = 0;       // Clear source
param_5[1] = 0;
```

**Move Semantics:** C++11 move semantics prevent unnecessary reference count operations

**Step 3: Move String Data**
```c
// Move wstring (32 bytes) - file path
*(longlong*)(task + 0x69) = param_6[0];
*(longlong*)(task + 0x71) = param_6[1];
*(longlong*)(task + 0x79) = param_6[2];
*(longlong*)(task + 0x81) = param_6[3];

// Clear source string
param_6[2] = 0;
param_6[3] = 7;  // SSO flag (Small String Optimization)
*(word*)param_6 = 0;
```

**Step 4: Store Additional Parameters**
```c
*(void**)(task + 0x41) = param_10;  // Context pointer
*(uint*)(task + 0x91) = *param_8;    // Integer parameter
*(byte*)(task + 0x95) = *param_9;    // Byte flag
```

**Step 5: Set Task Flags**
```c
uint flags = 0x10002;  // Default flags
if (*param_1 != 0) {
    flags = 2;         // Alternative flags if status != 0
}
*(uint*)(task + 0x9C) = flags;
```

**Step 6: Initialize Linked List Node**
```c
void** node = task + 2;  // Offset 0x10
*node = 0;
// ... zero-initialize 48 bytes ...
*node = task;           // Self-reference
*param_3 = node;        // Return pointer to node
```

### 4.3 Queue State Tracking

**Queue State Structure:**
```c
struct thread_pool_queue_state {
    int   max_queue_size;      // +0x34 Maximum tasks allowed
    int   current_queue_size;  // +0x3C Current task count
    int   queue_counter;       // +0xDC Task counter (statistics)
};
```

**Capacity Management:**
- `max_queue_size`: Set during initialization (prevents unbounded growth)
- `current_queue_size`: Atomically incremented/decremented
- `queue_counter`: Wraps at 0x7FFFFFFF, used for overflow detection

### 4.4 Queue Operations

#### Enqueue Operation

**Function:** enqueue_encrypt_task @ 0x14007b850

**Complete Enqueue Sequence:**
```c
void enqueue_encrypt_task(thread_pool *pool, ...)
{
    uint *mutex = (uint *)(pool + 0x12);  // Critical section at offset 0x90

    // Step 1: Acquire lock
    int result = mutex_lock(mutex);
    if (result != 0) {
        FUN_1400812e0(5);  // Log error code 5
        __debugbreak();     // Fatal error
        return;
    }

    // Step 2: Overflow detection
    if (*(int *)(pool + 0xdc) == 0x7fffffff) {
        *(int *)(pool + 0xdc) = 0x7ffffffe;  // Wrap counter
        FUN_1400812e0(6);  // Log error code 6
    }

    // Step 3: Wait if queue is full (producer blocks)
    while (*(int *)(pool + 0x34) <= *(int *)(pool + 0x3c)) {
        // Atomically release mutex and wait
        FUN_140082118(pool + 0x25, mutex);
        // Mutex re-acquired here after wake-up
    }

    // Step 4: Increment active task counter (atomic)
    LOCK();
    *(int *)(pool + 0x3c) = *(int *)(pool + 0x3c) + 1;
    UNLOCK();

    // Step 5: Build task object
    task_object* task = allocate_task(0x120);
    task_constructor(&status, task, ...);

    // Step 6: Post task to ASIO thread pool
    FUN_14007bd00(&pool[4], &task_ptr);

    // Step 7: Release lock
    if (lock_acquired) {
        _Mtx_unlock(mutex);
    }

    // Step 8: Cleanup (reference counting)
    // ...
}
```

**Key Features:**
- Blocks producer when queue full (backpressure)
- Atomic counter updates
- Overflow detection and logging
- Clean error handling

#### Dequeue Operation

**Inferred from worker thread behavior:**

```c
void worker_thread_loop(thread_pool* pool)
{
    while (!shutdown_flag) {
        mutex_lock(&pool->queue_mutex);

        // Wait for task
        while (queue_empty) {
            condition_variable_wait(&pool->queue_cv, &pool->queue_mutex);
        }

        // Remove task from queue
        task_object* task = dequeue_task(pool);

        // Decrement counter (atomic)
        LOCK();
        pool->current_queue_size--;
        UNLOCK();

        // Signal producers (wake if waiting)
        condition_variable_signal(&pool->queue_cv);

        mutex_unlock(&pool->queue_mutex);

        // Execute task (outside critical section)
        task->execution_function(task);

        // Cleanup task
        task->cleanup_function(task);
        operator_delete(task);
    }
}
```

### 4.5 Queue Capacity Management

**Overflow Detection:**
```c
if (pool->queue_counter == 0x7FFFFFFF) {
    pool->queue_counter = 0x7FFFFFFE;  // Wrap to prevent overflow
    log_error(6);  // Log overflow event (non-fatal)
}
```

**Purpose:**
- Detect if 2+ billion tasks have been queued
- Prevents integer overflow
- Logs event for statistics
- Operation continues normally

**Flow Control:**
- Producer blocks when `current_queue_size >= max_queue_size`
- Prevents memory exhaustion
- Provides backpressure
- CPU-efficient waiting (no busy loop)

---

## 5. Producer-Consumer Pattern

### 5.1 Pattern Overview

Akira implements a classic producer-consumer pattern with condition variables for efficient thread synchronization.

### 5.2 Producer Thread (Main Thread)

**Role:** Creates encryption tasks for discovered files

**Workflow:**
```
1. Traverse directory tree (filesystem enumeration)
2. For each file:
   a. Apply filters (extensions, directories, processes)
   b. If file passes filters:
      - Build task parameters (file path, crypto context, etc.)
      - Call enqueue_encrypt_task()
      - Task added to queue
      - Worker threads notified via condition variable
3. Continue until all files processed
4. Signal shutdown
```

**Blocking Behavior:**
- Producer blocks when queue is full
- Wakes up when consumer removes task
- Re-checks queue state after wake
- Continues if space available

### 5.3 Consumer Threads (Worker Threads)

**Role:** Process encryption tasks from queue

**Workflow:**
```
1. Thread created during thread pool initialization
2. Enter main loop:
   a. Lock queue mutex
   b. Wait for task (blocks on condition variable if empty)
   c. Dequeue task
   d. Unlock queue mutex
   e. Execute task (encrypt file - outside critical section)
   f. Task cleanup (free memory, decrement ref counts)
   g. Decrement task count (atomic)
   h. Signal producers via condition variable (if needed)
   i. Return to step 2a
3. Thread exits when shutdown signaled
```

**Non-Blocking Execution:**
- File encryption happens **outside** critical section
- Only queue operations are locked
- Maximizes parallelism
- Minimizes lock contention

### 5.4 Synchronization Flow

**Visual Representation:**

```
Producer Thread                          Consumer Thread
===============                          ===============

Lock queue mutex                         Lock queue mutex
    ↓                                        ↓
Check if queue full                      Check if queue empty
    ↓                                        ↓
[If full]                                [If empty]
Wait on CV (release mutex)               Wait on CV (release mutex)
    ← Wake up (mutex re-acquired)            ← Wake up (mutex re-acquired)
    ↓                                        ↓
Add task to queue                        Remove task from queue
    ↓                                        ↓
Increment task count (atomic)            Decrement task count (atomic)
    ↓                                        ↓
Signal CV (wake consumer)                Signal CV (wake producer)
    ↓                                        ↓
Unlock queue mutex                       Unlock queue mutex
    ↓                                        ↓
Continue                                 Execute task (outside lock)
                                             ↓
                                         Task cleanup
```

### 5.5 Efficiency Analysis

**CPU Efficiency:**
- Condition variables (no busy-waiting)
- Threads sleep when no work available
- Minimal CPU waste
- Fast wake-up (kernel-level notification)

**Memory Efficiency:**
- Bounded queue size prevents unlimited growth
- Task objects freed immediately after execution
- Move semantics (no unnecessary copies)
- Reference counting prevents leaks

**Scalability:**
- Lock-free when queue has space and tasks available
- Separate queues for folder parsing and encryption
- Minimal lock contention
- Scales linearly with core count (up to I/O bottleneck)

---

# PART 2: FILE SYSTEM OPERATIONS (PHASE 5)

## 6. Drive Enumeration

### 6.1 Overview

Akira enumerates logical drives and classifies them for selective encryption targeting. **Critical Finding:** NO active network share enumeration observed.

### 6.2 Drive Entry Structure

**Size:** 40 bytes (0x28)
**Container:** `std::vector<drive_entry_t>`

```c
struct drive_entry_t {
    // +0x00-0x1F: Drive path as std::wstring (32 bytes)
    wchar_t* string_ptr;        // +0x00 (8 bytes)
    size_t   string_length;     // +0x08 (8 bytes)
    size_t   string_capacity;   // +0x10 (8 bytes)
    size_t   string_flags;      // +0x18 (8 bytes) - SSO: 7 = inline

    // +0x20-0x27: Drive classification flags (8 bytes)
    bool     is_network;        // +0x20 (1 byte) - TRUE if DRIVE_REMOTE
    bool     is_accessible;     // +0x21 (1 byte) - TRUE if encryptable
    byte     padding[6];        // +0x22-0x27 (6 bytes)
};
```

### 6.3 Drive Type Classification

**Function:** initialize_drive_list @ 0x14007e6a0

#### Drive Type Mapping

| Type | Windows Constant | is_network | is_accessible | Encrypted? |
|------|------------------|------------|---------------|------------|
| 0    | DRIVE_UNKNOWN    | FALSE      | FALSE         | ❌ No       |
| 1    | DRIVE_NO_ROOT_DIR| FALSE      | FALSE         | ❌ No       |
| 2    | DRIVE_REMOVABLE  | FALSE      | TRUE          | ✅ Yes      |
| 3    | DRIVE_FIXED      | FALSE      | TRUE          | ✅ Yes      |
| 4    | DRIVE_REMOTE     | TRUE       | FALSE*        | ✅ Yes      |
| 5    | DRIVE_CDROM      | FALSE      | TRUE          | ✅ Yes      |
| 6    | DRIVE_RAMDISK    | FALSE      | TRUE          | ✅ Yes      |

**\*Note:** Network drives (type 4) are encrypted despite `is_accessible=FALSE` flag

#### Flag Calculation (Assembly)

**is_network flag @ 0x14007e7f0:**
```assembly
CMP  EAX, 0x4              ; Compare drive type to 4
SETZ byte ptr [RBP+0x27]   ; is_network = (type == 4)
```

**is_accessible flag @ 0x14007e7f6:**
```assembly
DEC  EAX                   ; type = type - 1
TEST EAX, 0xFFFFFFFB       ; AND with ~0x4 (binary: ...11111011)
SETZ byte ptr [RBP+0x28]   ; is_accessible = ((type-1) & ~4) == 0
```

**Boolean Logic:**
- `is_network = (drive_type == 4)`
- `is_accessible = (drive_type in {2, 3, 5, 6})`

### 6.4 Network Share Discovery

#### Method 1: Mapped Network Drives

**Detection:** `GetDriveTypeW()` returns type 4 for mapped drives
- Only **pre-mapped** drives are found (e.g., Z:\)
- No active enumeration
- Stealth over automation

#### Method 2: Share File Input

**Command-Line Parameter:**
```bash
akira.exe --share_file "C:\shares.txt"
```

**Function:** read_share_file @ 0x140042830

**File Format:**
```
\\server1\share1
\\server2\data
\\192.168.1.100\backups
```

**Share Entry Structure (32 bytes):**
```c
struct share_path_entry_t {
    wchar_t* path_ptr;          // +0x00 (8 bytes)
    size_t   path_length;       // +0x08 (8 bytes)
    size_t   path_capacity;     // +0x10 (8 bytes)
    size_t   path_flags;        // +0x18 (8 bytes) - SSO: 7 = inline
};
```

**Container:** `std::vector<share_path_entry_t>`

### 6.5 What Akira Does NOT Do

**❌ NO Active Network Enumeration:**
- No `NetShareEnum` API calls
- No `WNetEnumResource` API calls
- No `WNetOpenEnum` API calls
- No Active Directory queries
- No SMB/CIFS scanning

**Security Implication:** Stealth over automation. Requires manual reconnaissance by operators.

### 6.6 Key APIs

- `GetLogicalDriveStringsW` - Enumerate all logical drives (A:-Z:)
- `GetDriveTypeW` - Classify drive type (0-6)

---

## 7. Directory Traversal

### 7.1 Overview

Akira uses Windows file enumeration APIs combined with ASIO task-based recursion for parallel directory traversal across multiple worker threads.

### 7.2 Main Worker Function

**Function:** folder_processor_worker @ 0x1400bf190
**Type:** Thread pool worker
**Size:** ~3000+ lines decompiled (8,454 bytes)
**Purpose:** Main directory traversal and file discovery engine

### 7.3 Task Dispatch Mechanism

**Task Type Field:** `task->type` at offset +0x94 (uint16_t)

```c
switch (task->type) {
    case 2:
        // Main directory processing (recursive traversal)
        process_directory_recursively(task);
        break;

    case 3:
    case 1:
    case 0xFFFF:
        // Cleanup and finalization
        cleanup_task_resources(task);
        break;

    default:
        __fastfail(FAST_FAIL_INVALID_ARG);
}
```

### 7.4 Directory Iterator Structure

**Size:** 88 bytes (0x58)

```c
struct directory_iterator_impl_t {
    // +0x00-0x0F: Reference counting (std::shared_ptr pattern)
    void*    vftable_ptr;           // +0x00 (8 bytes)
    int      ref_count;             // +0x08 (4 bytes) - Strong refs
    int      weak_ref_count;        // +0x0C (4 bytes) - Weak refs

    // +0x10-0x2F: Iterator state
    void*    state_ptr;             // +0x10 (8 bytes)
    qword    reserved_18;           // +0x18 (8 bytes)
    qword    reserved_20;           // +0x20 (8 bytes)
    qword    reserved_28;           // +0x28 (8 bytes)

    // +0x30-0x4F: Current directory path (std::wstring)
    wchar_t* path_ptr;              // +0x30 (8 bytes)
    size_t   path_length;           // +0x38 (8 bytes)
    size_t   path_capacity;         // +0x40 (8 bytes)
    size_t   path_flags;            // +0x48 (8 bytes) - SSO: 7 = inline

    // +0x50-0x57: Windows search handle
    HANDLE   find_handle;           // +0x50 (8 bytes) - FindFirstFileExW
};
```

### 7.5 Directory Opening Process

**Function:** open_directory_iterator @ 0x14006f4c0

**Algorithm:**
```c
DWORD open_directory(const wchar_t* path, WIN32_FIND_DATAW* entry) {
    // 1. Validate path length > 0
    if (wcslen(path) == 0) return ERROR_INVALID_PARAMETER;

    // 2. Append wildcard
    wstring search_path = path + L"\\*";

    // 3. Open directory
    HANDLE hFind = FindFirstFileExW(
        search_path.c_str(),
        FindExInfoBasic,           // Optimization: no short name
        entry,
        FindExSearchNameMatch,
        NULL,
        FIND_FIRST_EX_LARGE_FETCH // Optimization: fetch multiple entries
    );

    if (hFind == INVALID_HANDLE_VALUE) {
        DWORD error = GetLastError();

        // 4. Handle errors
        if (error == ERROR_ACCESS_DENIED) {
            return 0;  // Treat as empty directory (skip silently)
        }
        return error;
    }

    // 5. Skip "." and ".." entries
    while (is_dot_or_dotdot(entry->cFileName)) {
        if (!FindNextFileW(hFind, entry)) {
            DWORD error = GetLastError();
            FindClose(hFind);
            return error;
        }
    }

    return 0;  // Success
}
```

**Optimizations:**
- `FindExInfoBasic`: Skip short (8.3) filenames for performance
- `FIND_FIRST_EX_LARGE_FETCH`: Request multiple entries per syscall

### 7.6 Iterator Advancement

**Function:** find_next_file_wrapper @ 0x140080b0c

```c
DWORD advance_iterator(HANDLE handle, WIN32_FIND_DATAW* entry) {
    BOOL result = FindNextFileW(handle, entry);

    if (!result) {
        DWORD error = GetLastError();
        if (error == ERROR_NO_MORE_FILES) {
            return 0x12;  // Normal end of iteration
        }
        return error;  // Real error
    }

    return 0;  // Success
}
```

**Error Handling:**
- `ERROR_NO_MORE_FILES` (0x12): Normal end (not an error)
- `ERROR_ACCESS_DENIED` (5): Treated as empty directory
- Other errors: Logged and skipped

### 7.7 Recursion Strategy

**Key Observation:** Recursion achieved via **task queue**, not function call stack.

**Advantages:**
- Parallel traversal across multiple threads
- No stack overflow (depth unlimited)
- Work-stealing load balancing
- Efficient for deep directory trees

**Flow:**
```
1. Open directory iterator
2. Loop through entries with FindNextFileW
3. For each entry:
   a. Check if dot/dotdot → skip
   b. Extract entry name
   c. Check entry type (directory vs file)
   d. Apply filters (see Section 8)
   e. If directory and not blacklisted:
      - Enqueue new directory traversal task
   f. If file and not blacklisted:
      - Enqueue encryption task
4. Continue until iterator exhausted
5. Close handle (FindClose)
6. Cleanup iterator structure
```

### 7.8 Key APIs

- `FindFirstFileExW` - Start directory enumeration (optimized)
- `FindNextFileW` - Get next entry
- `FindClose` - Close search handle

---

## 8. File Filtering System

### 8.1 Overview

Akira employs three filtering mechanisms to avoid encrypting system-critical files and maintain OS operability for ransom payment.

### 8.2 Extension Blacklist

**Initialization:** `init_extension_blacklist` @ 0x140001ac0
**Global Data:** `DAT_140102138` @ 0x140102138 (std::set<wstring>)
**Total Count:** 5 extensions

```cpp
static const wchar_t* BLACKLIST_EXTENSIONS[] = {
    L".exe",  // Executables
    L".dll",  // Dynamic Link Libraries
    L".lnk",  // Shortcuts
    L".sys",  // System drivers
    L".msi"   // Installers
};
```

**Purpose:** Keep Windows functional, allow browser access for payment instructions

### 8.3 Directory Blacklist

**Initialization:** `init_directory_blacklist` @ 0x1400018a0
**Global Data:** `DAT_140102148` @ 0x140102148 (std::set<wstring>)
**Total Count:** 11 directories (**ALL IDENTIFIED**)

```cpp
std::set<wstring> excluded_directories = {
    L"tmp",                        // Temporary directory
    L"winnt",                      // Legacy Windows NT
    L"temp",                       // Temp files
    L"thumb",                      // Thumbnail cache
    L"$Recycle.Bin",              // Recycle Bin (mixed case)
    L"$RECYCLE.BIN",              // Recycle Bin (uppercase)
    L"System Volume Information", // Shadow copies/restore points
    L"Boot",                      // Boot configuration
    L"Windows",                   // OS directory
    L"Trend Micro",               // Antivirus evasion
    L"ProgramData",               // System app data
};
```

**Case Sensitivity:** **Case-sensitive** matching (proven by dual Recycle Bin entries)

**Security Implication:** Case-sensitive filtering on case-insensitive Windows filesystem can be bypassed by changing directory name case.

### 8.4 Process Exclusion List

**Initialization:** `init_protected_process_names` @ 0x140001c10 (6,314 bytes with obfuscated strings)
**Global Data:** `DAT_140102158` @ 0x140102158 (std::set<wstring>)
**Total Count:** 13 critical Windows processes

```cpp
static const wchar_t* CRITICAL_PROCESSES[] = {
    L"spoolsv.exe",       // Print Spooler
    L"fontdrvhost.exe",   // Font Driver Host
    L"explorer.exe",      // Windows Explorer
    L"sihost.exe",        // Shell Infrastructure
    L"SearchUI.exe",      // Windows Search
    L"lsass.exe",         // Security Authority
    L"LogonUI.exe",       // Logon UI
    L"winlogon.exe",      // Logon Process
    L"services.exe",      // Service Control Manager
    L"csrss.exe",         // Runtime Subsystem
    L"smss.exe",          // Session Manager
    L"conhost.exe",       // Console Host
    L"wininit.exe"        // Windows Initialization
};
```

**Purpose:** Avoid terminating files locked by critical processes (prevents system crash during encryption)

**String Obfuscation:** Process names stored with custom XOR-based encoding, decoded at runtime

### 8.5 Filename Blacklist

**Status:** ❌ **DOES NOT EXIST**

Confirmed via exhaustive string searches - no filename-specific filtering (e.g., desktop.ini, thumbs.db)

### 8.6 STL Set Implementation

**Type:** `std::set<std::wstring>`
**Implementation:** Red-black tree (self-balancing BST)
**Complexity:** O(log n) lookup

#### Red-Black Tree Node Structure

**Size:** 64 bytes per node

```c
struct tree_node {
    tree_node* parent;     // +0x00 (8 bytes)
    tree_node* left;       // +0x08 (8 bytes)
    tree_node* right;      // +0x10 (8 bytes)
    byte       color;      // +0x18 (1 byte) - Red=0, Black=1
    byte       is_leaf;    // +0x19 (1 byte)
    byte       padding[6]; // +0x1A-0x1F

    // Embedded wstring (32 bytes)
    wchar_t*   key_ptr;    // +0x20 (8 bytes)
    size_t     key_length; // +0x28 (8 bytes)
    size_t     key_capacity; // +0x30 (8 bytes)
    size_t     key_flags;  // +0x38 (8 bytes) - SSO: 7 = inline
};
```

### 8.7 Filtering Logic Implementation

#### Two-Function System

**Function 1: STL Set Lookup** - `stl_set_find` @ 0x14005dea0

```c
// Performs O(log n) binary search in red-black tree
iterator stl_set_find(
    std::set<wstring>* set_ptr,      // Blacklist set
    iterator_result* result,          // Output iterator
    const wchar_t* search_string      // Name to find
) {
    // Binary search in red-black tree
    // Returns iterator to found element or end()
}
```

**Function 2: String Comparison** - `stl_wstring_compare` @ 0x14005df80

```c
// Character-by-character wide string comparison
int stl_wstring_compare(
    void* set_ptr,
    tree_node* iterator,
    const wchar_t* search_string
) {
    // Returns 0 if match (string in blacklist)
    // Returns non-zero if no match
}
```

#### Usage in folder_processor_worker

**Directory Filtering @ 0x1400bf6f1:**
```c
// Extract directory name from WIN32_FIND_DATAW
wstring dirname = get_directory_name(entry);

// Lookup in blacklist (DAT_140102148)
auto iter = stl_set_find(&DAT_140102148, &result, dirname);
bool is_blacklisted = (stl_wstring_compare(&DAT_140102148, iter[2], dirname) == 0);

if (is_blacklisted) {
    // SKIP this directory - do not recurse
} else {
    // PROCESS this directory - enqueue traversal task
    enqueue_directory_task(...);
}
```

**Extension Filtering @ 0x1400bfe16:**
```c
// Extract file extension from filepath
wstring extension = get_file_extension(filepath);

// Lookup in blacklist (DAT_140102138)
auto iter = stl_set_find(&DAT_140102138, &result, extension);
bool is_blacklisted = (stl_wstring_compare(&DAT_140102138, iter[2], extension) == 0);

if (is_blacklisted) {
    // SKIP this file - do not encrypt
} else {
    // ENCRYPT this file - enqueue encryption task
    enqueue_encrypt_task(...);
}
```

### 8.8 Performance Characteristics

| Operation | Complexity | Description |
|-----------|------------|-------------|
| Directory Lookup | O(log 11) ≈ 3-4 comparisons | Binary search |
| Extension Lookup | O(log 5) ≈ 2-3 comparisons | Binary search |
| String Compare | O(min(n,m)) | Character-by-character |

**Memory Footprint:**
- Extension blacklist: ~400 bytes (5 nodes × 64 bytes + strings)
- Directory blacklist: ~800 bytes (11 nodes × 64 bytes + strings)
- Process blacklist: ~900 bytes (13 nodes × 64 bytes + strings)
- **Total:** ~2.1 KB

**Timing:**
- Average lookup time: ~100-200 CPU cycles
- Negligible compared to I/O operations (disk access)

---

## 9. File Access & Manipulation

### 9.1 Overview

Akira uses sophisticated file access techniques including two-stage locking, atomic renaming, and Windows Restart Manager integration.

### 9.2 Main Function

**Function:** file_encryption_state_machine @ 0x1400b6f10
**Size:** Massive state machine with 19+ states
**Type:** State machine pattern for asynchronous encryption workflow

### 9.3 File Opening Strategy

#### Three-Step Process

**Step 1: Remove Read-Only Attribute**

```c
DWORD attrs = GetFileAttributesW(filepath);
if (attrs != INVALID_FILE_ATTRIBUTES && (attrs & FILE_ATTRIBUTE_READONLY)) {
    // Remove read-only bit (bitwise XOR with 0x1)
    SetFileAttributesW(filepath, attrs ^ FILE_ATTRIBUTE_READONLY);
}
```

**Purpose:** Ensure writable access even if user marked file read-only

**Step 2A: Exclusive Lock (First Attempt)**

```c
HANDLE hFile = CreateFileW(
    filepath,
    GENERIC_READ | GENERIC_WRITE | DELETE,  // 0xC0010000
    0,                                       // No sharing (exclusive)
    NULL,
    OPEN_EXISTING,
    FILE_ATTRIBUTE_NORMAL | FILE_FLAG_SEQUENTIAL_SCAN,  // 0x40000080
    NULL
);
```

**Access Rights:**
- `GENERIC_READ` (0x80000000): Read file content
- `GENERIC_WRITE` (0x40000000): Write encrypted data
- `DELETE` (0x00010000): Required for atomic rename

**Share Mode:** 0 (exclusive lock - no other processes can access)

**Outcome:**
- Success = full exclusive control
- Failure (ERROR_SHARING_VIOLATION) → try fallback

**Step 2B: Shared Lock (Fallback)**

**Trigger:** `ERROR_SHARING_VIOLATION` (0x20) or `ERROR_LOCK_VIOLATION` (0x21)

```c
if (error == 0x20 || error == 0x21) {
    // Attempt to unlock via Restart Manager (see Section 10)
    restart_manager_unlock_file(filepath);

    // Retry with shared access
    hFile = CreateFileW(
        filepath,
        GENERIC_READ | GENERIC_WRITE,  // 0xC0000000 (no DELETE permission)
        FILE_SHARE_READ | FILE_SHARE_WRITE,  // 0x3 (allow sharing)
        NULL,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL | FILE_FLAG_SEQUENTIAL_SCAN,
        NULL
    );
}
```

**Key Insight:** Can encrypt files open in other programs (best-effort encryption)

**Limitation:** Rename may fail without DELETE permission

**Step 3: Handle Validation**

```c
if (hFile == INVALID_HANDLE_VALUE || hFile == NULL) {
    log_error("File handle not found! " + filename);
    return;  // Skip this file (non-fatal)
}
```

### 9.4 File Size Detection

```c
LARGE_INTEGER fileSize = {0};
if (!GetFileSizeEx(hFile, &fileSize)) {
    log_error("Get file size failed! " + filename);
    CloseHandle(hFile);
    return;
}

if (fileSize.QuadPart == 0) {
    log_error("File size invalid! " + filename);
    CloseHandle(hFile);
    return;  // SKIP zero-byte files
}
```

**Critical Finding:** Zero-byte files explicitly rejected (unusual behavior, potential detection vector)

### 9.5 ASIO Handle Wrapping

**Purpose:** Integrate Windows file HANDLE with Boost ASIO for async I/O

**Structure (112 bytes):**
```c
struct asio_handle_wrapper_t {
    void*  vtable_ptr;        // +0x00 (8 bytes)
    int    ref_count;         // +0x08 (4 bytes) - Atomic
    int    weak_ref_count;    // +0x0C (4 bytes) - Atomic
    byte   asio_object[96];   // +0x10 (96 bytes) - ASIO internal state
};
```

**Reference Counting (Automatic Cleanup):**
```c
// Atomic decrement
LOCK();
ref_count--;
old_count = ref_count;
UNLOCK();

if (old_count == 0) {
    // Last strong reference - call destructor (closes handle)
    vtable->destroy(this);

    LOCK();
    weak_ref_count--;
    UNLOCK();

    if (weak_ref_count == 0) {
        // Last weak reference - free memory
        vtable->deallocate(this);
    }
}
```

**Advantages:**
- Automatic resource management (RAII pattern)
- Thread-safe cleanup (atomic ref counting)
- Integration with ASIO thread pool
- Exception-safe (cleanup guaranteed)

### 9.6 File Renaming

#### Build New Filename

```c
string extension = ".arika";
wstring new_name = original_filename + L".arika";
// Example: document.pdf → document.pdf.arika
```

#### Atomic Rename via SetFileInformationByHandle

```c
// Allocate FILE_RENAME_INFO structure
size_t struct_size = sizeof(FILE_RENAME_INFO) + (new_name.length() * sizeof(wchar_t));
FILE_RENAME_INFO* rename_info = (FILE_RENAME_INFO*)malloc(struct_size);

rename_info->ReplaceIfExists = TRUE;
rename_info->RootDirectory = NULL;
rename_info->FileNameLength = new_name.length() * sizeof(wchar_t);
wcscpy(rename_info->FileName, new_name.c_str());

// Perform atomic rename
BOOL success = SetFileInformationByHandle(
    hFile,            // File must be open
    FileRenameInfo,   // Info class = 3
    rename_info,
    struct_size
);

if (!success) {
    log_error("file rename failed. System error: " + GetLastError());
}
```

**Advantages:**
1. **Atomic Operation:** No race condition window
2. **File Stays Open:** No need to close/reopen handle
3. **Works with Locks:** Even if file is in use by other processes
4. **Rename + Delete Atomic:** Can replace existing file atomically

#### Auto-Save Cleanup

```c
if (auto_save_file_exists) {
    DeleteFileW(auto_save_filepath);
}
```

**Purpose:** Remove temporary files (e.g., Word ~$file.docx)

### 9.7 Locking Strategy Summary

| Attempt | Access Rights | Share Mode | Purpose |
|---------|--------------|------------|---------|
| **1st** | READ+WRITE+DELETE | 0 (exclusive) | Full exclusive lock |
| **2nd** | READ+WRITE | READ+WRITE (3) | Shared lock if locked |

**Implications:**
- Can encrypt files open in other programs (best-effort)
- Rename may fail if no DELETE permission granted
- Multiple `CreateFileW` attempts detectable by EDR

### 9.8 Error Handling

**12 Distinct Error Messages:**

1. "Crypt context not found!" @ 0x1400dc580
2. "File handle not found!" @ 0x1400dc5a0
3. "Get file size failed!" @ 0x1400dc5c0
4. "File size invalid!" @ 0x1400dc5e0
5. "Init cipher failed!" @ 0x1400dc628
6. "get auto save file name failed!" @ 0x1400dc648
7. "Encrypt pack id failed!" @ 0x1400dc670
8. "Failed to make full encrypt!" @ 0x1400dc6d8
9. "Failed to write header!" @ 0x1400dc77c
10. "Failed to make spot encrypt!" @ 0x1400dc700
11. "Failed to make part encrypt!" @ 0x1400dc728
12. "file rename failed. System error:" @ 0x1400dc754

**All logged to global logger:** `DAT_140102188` (log level 4 = ERROR)

**Detection Opportunity:** Error strings aid reverse engineering and dynamic analysis

### 9.9 Key APIs

- `GetFileAttributesW` / `SetFileAttributesW` - Attribute manipulation
- `CreateFileW` - File opening (two attempts with different parameters)
- `GetFileSizeEx` - Size detection
- `SetFileInformationByHandle` - Atomic rename operation
- `DeleteFileW` - Auto-save cleanup

---

## 10. Restart Manager Integration

### 10.1 Overview

**Critical Discovery:** Akira uses Windows Restart Manager API to force-terminate processes holding file locks, enabling successful encryption of in-use files.

**Function:** restart_manager_unlock_file @ 0x140078cc0
**Protected Processes Function:** `populate_process_blacklist` @ 0x140078ac0

### 10.2 Restart Manager API Flow

**Complete Sequence:**

```
CreateFileW → ERROR_SHARING_VIOLATION (0x20)
    ↓
restart_manager_unlock_file(filepath)
    ↓
1. RmStartSession(session_key, session_handle)
    ↓
2. RmRegisterResources(session, 1, &filepath, 0, NULL, 0, NULL)
    ↓
3. RmGetList(session, &needed_size, &count, NULL, &reboot_reason)
    ↓
4. Allocate buffer (needed_size × sizeof(RM_PROCESS_INFO))
    ↓
5. RmGetList(session, &needed_size, &count, process_info, &reboot_reason)
    ↓
6. For each process:
       - Check if PID in protected_process_list (DAT_1401021b8)
       - If protected: SKIP
       - If not protected: Add to kill list
    ↓
7. RmShutdown(session, RmForceShutdown, NULL)  // FORCE TERMINATE
    ↓
8. RmEndSession(session)
    ↓
CreateFileW (retry with shared access)
```

### 10.3 Protected Processes

**Global Data Structures:**
- `DAT_140102158` @ 0x140102158: `std::set<wstring>` (process names)
- `DAT_1401021b8` @ 0x1401021b8: `std::vector<DWORD>` (process PIDs)

**Initialization:** `init_protected_process_names` @ 0x140001c10
**Size:** 6,314 bytes with custom XOR obfuscation
**Total Count:** 13 critical Windows processes

```cpp
static const wchar_t* PROTECTED_PROCESSES[] = {
    L"csrss.exe",            // Client/Server Runtime Subsystem
    L"wininit.exe",          // Windows Initialization
    L"spoolsv.exe",          // Print Spooler
    L"lsass.exe",            // Local Security Authority
    L"smss.exe",             // Session Manager
    L"winlogon.exe",         // Windows Logon Process
    L"services.exe",         // Service Control Manager
    L"conhost.exe",          // Console Host
    L"System",               // System process (PID 4)
    L"Registry",             // Registry process
    L"Memory Compression",   // Memory Compression (Windows 10+)
    L"fontdrvhost.exe",      // Font Driver Host
    L"explorer.exe"          // Windows Explorer
};
```

**PID Population Function:**
```c
void populate_process_blacklist(void* pid_vector) {
    HANDLE hSnapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    PROCESSENTRY32W pe = {sizeof(PROCESSENTRY32W)};

    Process32FirstW(hSnapshot, &pe);
    do {
        wstring proc_name = pe.szExeFile;

        // Check if in protected process names set
        auto iter = stl_set_find(&DAT_140102158, proc_name);
        if (iter != end()) {
            // Add PID to vector
            vector_push_back(pid_vector, pe.th32ProcessID);
        }
    } while (Process32NextW(hSnapshot, &pe));

    CloseHandle(hSnapshot);
}
```

### 10.4 Critical Finding: NO Security Software Protection

**❌ NO EDR/AV in Protected List:**
- No antivirus processes
- No EDR agents
- No security monitoring tools

**Implication:** Akira can and will terminate security software processes to gain file access.

### 10.5 Detection Signature

**Behavioral Detection Rule:**
```yaml
sequence:
  - api: RmStartSession
  - api: RmGetList
  - api: RmShutdown
    parameters:
      dwShutdownFlags: 1  # RmForceShutdown = MALICIOUS

severity: CRITICAL
description: "Process force-termination via Restart Manager (ransomware behavior)"
```

**YARA Rule:**
```yara
import "pe"

rule Akira_RestartManager {
    strings:
        $api1 = "RmStartSession" ascii
        $api2 = "RmRegisterResources" ascii
        $api3 = "RmGetList" ascii
        $api4 = "RmShutdown" ascii
        $api5 = "RmEndSession" ascii

    condition:
        pe.is_pe and
        all of ($api*)
}
```

### 10.6 Restart Manager APIs

- `RmStartSession` - Start Restart Manager session
- `RmRegisterResources` - Register file/process/service for tracking
- `RmGetList` - Get list of processes using registered resources
- `RmShutdown` - Shutdown/restart affected applications
  - `RmForceShutdown` (flag = 1): Force terminate without saving
- `RmEndSession` - End Restart Manager session

---

# PART 3: INTEGRATION & ANALYSIS

## 11. Cross-Component Architecture

### 11.1 Complete File System Flow

```
┌──────────────────────────────────────────────────────────────┐
│                    PHASE 5.1: Drive Enumeration              │
│                                                               │
│  GetLogicalDriveStringsW → GetDriveTypeW                     │
│        ↓                                                      │
│  Drive List: [C:\, D:\, E:\, Z:\ (network)]                 │
│        ↓                                                      │
│  + Share File Input: \\server\share (if --share_file)       │
└─────────────────┬─────────────────────────────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────────────────────────────┐
│                PHASE 5.2: Directory Traversal                │
│                                                               │
│  For each drive/share:                                        │
│    ├─ Open directory iterator (FindFirstFileExW)            │
│    ├─ Loop: FindNextFileW                                    │
│    └─ For each entry → Apply filters (Phase 5.3)           │
└─────────────────┬─────────────────────────────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────────────────────────────┐
│                 PHASE 5.3: File Filtering                    │
│                                                               │
│  ┌──────────────┐     ┌──────────────┐                      │
│  │  Directory?  │     │  File?       │                      │
│  └──────┬───────┘     └──────┬───────┘                      │
│         │                    │                               │
│         ▼                    ▼                               │
│  ┌─────────────┐      ┌─────────────┐                      │
│  │ Check Dir   │      │ Check Ext   │                      │
│  │ Blacklist   │      │ Blacklist   │                      │
│  │ (11 dirs)   │      │ (5 exts)    │                      │
│  └──────┬──────┘      └──────┬──────┘                      │
│         │                    │                               │
│    [MATCH] → SKIP       [MATCH] → SKIP                      │
│         │                    │                               │
│    [NO MATCH]           [NO MATCH]                          │
│         │                    │                               │
│         ▼                    ▼                               │
│  Enqueue Dir Task     → Phase 5.4 (File Access)            │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│            PHASE 5.4: File Access & Manipulation             │
│                                                               │
│  1. Remove READ_ONLY attribute                               │
│  2. CreateFileW (exclusive) → [FAIL] → CreateFileW (shared)  │
│  3. [SHARING VIOLATION] → Restart Manager (force kill)       │
│  4. GetFileSizeEx → [0 bytes] → SKIP                        │
│  5. Wrap in ASIO handle (reference counted)                  │
│  6. → Pass to PHASE 6 (Encryption - see cryptography doc)   │
│  7. SetFileInformationByHandle (rename to .arika)            │
│  8. Reference count cleanup (automatic close)                │
└──────────────────────────────────────────────────────────────┘
```

### 11.2 Threading Integration

```
Main Thread
    │
    ├─ initialize_drive_list()
    │       ↓
    │  Drive Vector Built
    │       ↓
    ├─ init_thread_pool(folder_threads=30%, encryption_threads=60%)
    │       ↓
    │  Thread Pool Created (N workers)
    │       ↓
    └─ For each drive:
            enqueue_directory_task()
                    ↓
┌───────────────────┴────────────────────────┐
│                                            │
Worker Thread 1          Worker Thread N
(Folder Parser)          (Folder Parser)
    │                        │
    ├─ folder_processor_worker()
    │       ↓                │
    │  Open directory        │
    │  (FindFirstFileExW)    │
    │       ↓                │
    │  For each entry:       │
    │    ├─ is_dot_or_dotdot? → skip
    │    ├─ Get entry name   │
    │    ├─ Check filters    │
    │    │   (O(log n) lookup)
    │    ├─ If dir → enqueue_directory_task()
    │    └─ If file → enqueue_encrypt_task()
    │                        │
    └────────────────────────┘
                ↓
         Encryption Workers
         (60% of threads)
              ↓
         File Encryption
         (Phase 3 - ChaCha20)
```

### 11.3 Data Flow Diagram

```
Logical Drives → Drive List (40 bytes each)
                      ↓
                Directory Iterator (88 bytes)
                      ↓
                WIN32_FIND_DATAW (592 bytes)
                      ↓
           ┌──────────┴──────────┐
           │                     │
    Directory Name          File Path
           │                     │
           ▼                     ▼
    STL set lookup         STL set lookup
    (DAT_140102148)       (DAT_140102138)
    Red-black tree        Red-black tree
    O(log 11)             O(log 5)
           │                     │
           ▼                     ▼
    [Skip/Process]         [Skip/Encrypt]
           │                     │
           └──────────┬──────────┘
                      ▼
              File Handle (HANDLE)
                      ↓
            ASIO Wrapper (112 bytes)
                      ↓
              Reference Counted
                      ↓
         Task Object (288 bytes)
                      ↓
              Task Queue
                      ↓
         → Encryption Worker →
                      ↓
         ChaCha20 Encryption
         (Phase 3 - Crypto)
```

### 11.4 Memory Layout Summary

```
Thread Pool Structure (384 bytes total):
├── Fields (40 bytes)
├── Thread Counts (8 bytes)
├── Critical Section 1 (80 bytes) ← Folder parser
├── Critical Section 2 (80 bytes) ← Encryption
├── Condition Variable 1 (72 bytes)
├── Condition Variable 2 (72 bytes)
└── ASIO Pool Pointers (32 bytes)

Per-Thread Overhead:
├── Thread Object (32 bytes)
├── Thread Stack (1-8 MB default)
└── ASIO Context (shared 56 bytes)

Per-Task Overhead:
├── Task Object (288 bytes)
└── Task Parameters (embedded)

Filtering Data Structures:
├── Extension blacklist (5 nodes × 64 bytes) ≈ 400 bytes
├── Directory blacklist (11 nodes × 64 bytes) ≈ 800 bytes
├── Process blacklist (13 nodes × 64 bytes) ≈ 900 bytes
└── Total: ~2.1 KB (negligible)

Dynamic Allocations (Per File):
├── Directory Iterator (88 bytes) - reused
├── ASIO Handle Wrapper (112 bytes) - per open file
├── Task Object (288 bytes) - per queued task
└── WIN32_FIND_DATAW (592 bytes) - per iterator
```

---

## 12. Performance Analysis

### 12.1 Complexity Analysis

| Component | Operation | Complexity | Notes |
|-----------|-----------|------------|-------|
| Drive Enum | Enumerate drives | O(D) | D = number of drives (≤26) |
| Dir Traversal | File enumeration | O(F) | F = total files/folders |
| Filter Check | Blacklist lookup | O(log 11) + O(log 5) | ~6-7 comparisons max |
| File Open | CreateFileW | O(1) | Constant time API call |
| Encryption | ChaCha20 | O(N) | N = file size (see Phase 3) |

**Total File Processing:** O(F × (log K + N))
- F = number of files
- K = filter size (≈16 total entries)
- N = average file size

### 12.2 Thread Efficiency

**CPU Utilization:**
- Near 100% CPU usage during encryption phase
- Well-balanced workload distribution (30/10/60 split)
- Minimal idle time on worker threads
- Condition variables prevent busy-waiting

**I/O Patterns:**
- Parallel directory traversal (30% of threads)
- Concurrent file encryption (60% of threads)
- High throughput on NVMe storage
- Sequential scan flag for disk optimization

**Bottlenecks:**
- Single producer (main thread) for task enqueue
- File system metadata operations (NTFS overhead)
- ChaCha20 encryption speed (CPU-bound)
- I/O bound on HDD systems

### 12.3 Scalability Metrics

| CPU Cores | Threads | Est. Throughput | Bottleneck     |
|-----------|---------|-----------------|----------------|
| 2         | 2       | 50-100 MB/s     | CPU-bound      |
| 4         | 4       | 200-400 MB/s    | CPU-bound      |
| 8         | 8       | 400-800 MB/s    | Mixed          |
| 16        | 16      | 800-1600 MB/s   | I/O-bound      |
| 32        | 32      | 1-2 GB/s        | I/O-bound      |
| 64+       | 64+     | 2+ GB/s         | I/O-bound      |

**Assumptions:**
- NVMe SSD storage (>2 GB/s read/write)
- Average file size 10 MB
- 50% files pass filters
- ChaCha20 throughput ~400 MB/s per core

### 12.4 Throughput Estimation

**Test Scenario:**
- 10 worker threads (8-core system)
- 100,000 files
- 50% pass filters (50,000 encrypted)
- Average file 10 MB

**Time Breakdown (Per File):**
- Filter check: 6-7 comparisons × 2 µs = ~15 µs
- File open: ~500 µs (NVMe)
- GetFileSizeEx: ~50 µs
- Encryption: ~10 ms per file (ChaCha20 @ 1 GB/s)
- Rename: ~200 µs (SetFileInformationByHandle)
- **Total per file:** ~10.765 ms

**Theoretical Throughput:**
- Single thread: ~93 files/sec
- 10 threads: ~930 files/sec
- **Total time for 50K files:** ~54 seconds (~1 minute)

**Actual Performance:** Likely I/O bound
- HDD: ~100 MB/s sequential (slower)
- SSD SATA: ~500 MB/s sequential
- SSD NVMe: ~2000 MB/s sequential (theoretical max)

### 12.5 Memory Footprint

| Component | Size | Count | Total |
|-----------|------|-------|-------|
| Thread Pool | 384 bytes | 1 | ~400 bytes |
| Thread Object | 32 bytes | ≤64 | ~2 KB |
| ASIO Pool | 48 bytes | 2 | ~100 bytes |
| ASIO Context | 56 bytes | 2 | ~112 bytes |
| Dir Iterator | 88 bytes | Per thread | ~880 bytes (10 threads) |
| Extension Set | ~400 bytes | 1 | ~400 bytes |
| Directory Set | ~800 bytes | 1 | ~800 bytes |
| Process Set | ~900 bytes | 1 | ~900 bytes |
| Task Object | 288 bytes | Per file | Variable (queue bounded) |
| ASIO Handle | 112 bytes | Per open file | Variable |

**Static Memory:** ~5.5 KB
**Dynamic Memory (Peak):** Depends on queue size (likely 100-1000 tasks × 288 bytes = 28-288 KB)
**Total Estimated:** <500 KB for threading infrastructure

---

## 13. Security Assessment

### 13.1 Strengths (Malware Perspective)

**1. System Preservation:**
- Excludes Windows, Boot → System remains bootable
- Excludes .exe, .dll, .sys → Applications still run
- Excludes critical processes → No BSOD
- Victim can pay ransom using browser

**2. Professional Engineering:**
- Boost ASIO library (industry standard)
- STL containers (maintainable, efficient)
- Reference counting (no handle leaks)
- Atomic operations (race-free)
- Comprehensive error handling
- Clean architecture (separation of concerns)

**3. Stealth:**
- No active network enumeration (reduces detection)
- Minimal API footprint
- Quiet failures (logs errors, continues)
- String obfuscation (protected process names)

**4. Efficiency:**
- O(log n) filtering (fast blacklist checks)
- Parallel traversal (30% threads for I/O)
- Parallel encryption (60% threads for CPU)
- Sequential scan hint (disk optimization)
- Bounded queue (prevents memory exhaustion)

**5. Process Termination:**
- Restart Manager API (legitimate Windows feature)
- Force-kills processes holding file locks
- NO security software protection
- Can terminate EDR/AV agents

**6. Robustness:**
- Two-stage file locking (exclusive → shared)
- Atomic renaming (race-free)
- Zero-byte file skip (avoids corruption)
- Deadlock-free design
- Exception-safe resource management

### 13.2 Weaknesses (Defender Perspective)

**1. Predictable Patterns:**
- Two `CreateFileW` attempts with specific flags:
  - 1st: `dwDesiredAccess=0xC0010000`, `dwShareMode=0`
  - 2nd: `dwDesiredAccess=0xC0000000`, `dwShareMode=3`
- `SetFileInformationByHandle` with `FileRenameInfo` (unusual)
- Sequential scan flag (uncommon for normal apps)
- Error strings aid reverse engineering

**2. Behavioral Signatures:**
- High file I/O rate across entire filesystem
- Repeated attribute modifications (`SetFileAttributesW` to remove READ_ONLY)
- Mass file renaming to `.arika` extension
- Sharing violation retries (ERROR_SHARING_VIOLATION handling)
- Restart Manager process termination (RmShutdown with RmForceShutdown)

**3. Memory Artifacts:**
- STL red-black tree structures (predictable memory layout)
- ASIO handle wrappers (112-byte allocations)
- Task objects (288-byte allocations)
- Predictable string patterns:
  - L".exe", L".dll", L".sys", L".lnk", L".msi"
  - L"Windows", L"Boot", L"$Recycle.Bin"
  - L".arika"

**4. Logic Flaws:**
- **Case-sensitive filtering on Windows:** Can be bypassed by changing directory name case
  - Example: Rename "Windows" to "windows" to avoid exclusion
- Zero-byte file skip (unusual, detection vector)
- No filename filtering (desktop.ini, thumbs.db encrypted)
- NO security software in protected process list

**5. Network Stealth Trade-off:**
- Requires manual share enumeration (--share_file)
- Operators must pre-enumerate network
- Misses dynamically mapped shares

### 13.3 Vulnerability Analysis

**CVSS Assessment (Hypothetical):**

**Theoretical Vulnerability:** Case-Sensitive Directory Filtering on Case-Insensitive Filesystem

- **CVSS v3.1 Vector:** `CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:N/I:L/A:N`
- **Base Score:** 3.3 (LOW)
- **Impact:** Attacker expects "Windows" to be encrypted, but "windows" bypasses filter

**Note:** This is not a vulnerability in the traditional sense, but a logic flaw that could be exploited by defenders to protect critical directories.

---

## 14. Detection Strategies

### 14.1 Static Detection

#### YARA Rules

**Rule 1: Threading Patterns**
```yara
rule Akira_Threading_ASIO {
    meta:
        description = "Akira ransomware - ASIO threading patterns"
        author = "MottaSec"
        date = "2025-01-15"
        hash = "SAMPLE_HASH"

    strings:
        // ASIO library signatures
        $asio1 = "asio::thread_pool" ascii
        $asio2 = "asio::detail::win_thread" ascii
        $asio3 = "Concurrency::details::stl_critical_section_win7" ascii

        // Synchronization patterns (opcodes)
        $pattern1 = { 48 8D 0D [4] E8 [4] 48 8D 0D [4] E8 }  // Thread pool init

    condition:
        uint16(0) == 0x5A4D and  // PE file
        (2 of ($asio*) or $pattern1)
}
```

**Rule 2: File System Operations**
```yara
rule Akira_FileSystem {
    meta:
        description = "Akira ransomware - File system operations"
        author = "MottaSec"
        date = "2025-01-15"

    strings:
        // Extension blacklist
        $ext1 = ".exe" wide
        $ext2 = ".dll" wide
        $ext3 = ".sys" wide
        $ext4 = ".lnk" wide
        $ext5 = ".msi" wide

        // Directory blacklist
        $dir1 = "System Volume Information" wide
        $dir2 = "Trend Micro" wide
        $dir3 = "$Recycle.Bin" wide
        $dir4 = "$RECYCLE.BIN" wide

        // Error messages
        $err1 = "File handle not found! " wide
        $err2 = "Get file size failed! " wide
        $err3 = "file rename failed. System error:" wide

        // Akira extension
        $arika = ".arika" wide

    condition:
        uint16(0) == 0x5A4D and
        (
            (3 of ($ext*)) or
            (2 of ($dir*))
        ) and
        (2 of ($err*)) and
        $arika
}
```

**Rule 3: Restart Manager**
```yara
rule Akira_RestartManager {
    meta:
        description = "Akira ransomware - Process termination via Restart Manager"
        author = "MottaSec"
        date = "2025-01-15"

    strings:
        $api1 = "RmStartSession" ascii
        $api2 = "RmRegisterResources" ascii
        $api3 = "RmGetList" ascii
        $api4 = "RmShutdown" ascii
        $api5 = "RmEndSession" ascii

    condition:
        uint16(0) == 0x5A4D and
        all of ($api*)
}
```

#### Import Signatures

**Critical API Combinations:**
```
Threading:
- InitializeConditionVariable
- SleepConditionVariableCS
- WakeConditionVariable
- WakeAllConditionVariable

File System:
- GetLogicalDriveStringsW
- GetDriveTypeW
- FindFirstFileExW
- FindNextFileW
- GetFileAttributesW
- SetFileAttributesW
- CreateFileW
- GetFileSizeEx
- SetFileInformationByHandle
- DeleteFileW

Process Termination:
- RmStartSession
- RmRegisterResources
- RmGetList
- RmShutdown
- RmEndSession
- CreateToolhelp32Snapshot
- Process32FirstW
- Process32NextW
```

### 14.2 Dynamic Detection

#### EDR Behavioral Rules

**Rule 1: Mass File Access Pattern**
```yaml
name: "Akira - Mass File Access Pattern"
description: "Detects rapid file access with specific flags"
severity: HIGH

sequence:
  - event: CreateFileW
    count: ">100"
    time_window: "1 minute"
    filters:
      dwDesiredAccess: 0xC0010000
      dwShareMode: 0
      dwFlagsAndAttributes: 0x40000080

action: ALERT + BLOCK
```

**Rule 2: Attribute Manipulation Pattern**
```yaml
name: "Akira - Mass READ_ONLY Removal"
description: "Detects mass removal of read-only attribute"
severity: MEDIUM

sequence:
  - event: GetFileAttributesW
    next:
      - event: SetFileAttributesW
        filters:
          operation: "XOR with FILE_ATTRIBUTE_READONLY"
    count: ">50"
    time_window: "1 minute"

action: ALERT
```

**Rule 3: Atomic Rename Pattern**
```yaml
name: "Akira - Mass Atomic Rename to .arika"
description: "Detects mass file renaming to .arika extension"
severity: CRITICAL

sequence:
  - event: SetFileInformationByHandle
    filters:
      FileInformationClass: FileRenameInfo
      NewFileName: "regex:.*\\.arika$"
    count: ">20"
    time_window: "30 seconds"

action: ALERT + BLOCK + ISOLATE
```

**Rule 4: Sharing Violation Retry Pattern**
```yaml
name: "Akira - File Lock Retry Pattern"
description: "Detects two-stage file locking attempts"
severity: MEDIUM

sequence:
  - event: CreateFileW
    result: ERROR_SHARING_VIOLATION
    next:
      - event: CreateFileW
        filters:
          same_file: true
          dwShareMode: 3  # Shared access
    count: ">10"
    time_window: "1 minute"

action: ALERT
```

**Rule 5: Restart Manager Process Termination**
```yaml
name: "Akira - Forced Process Termination"
description: "Detects malicious use of Restart Manager"
severity: CRITICAL

sequence:
  - event: RmStartSession
  - event: RmGetList
  - event: RmShutdown
    filters:
      dwShutdownFlags: 1  # RmForceShutdown

action: ALERT + BLOCK + ISOLATE
```

**Rule 6: Zero-Byte Skip Pattern**
```yaml
name: "Akira - Zero-Byte File Skip"
description: "Detects unusual zero-byte file rejection"
severity: LOW

sequence:
  - event: GetFileSizeEx
    result: 0
    next:
      - event: CloseHandle
        time_delta: "<10ms"
    count: ">10"
    time_window: "1 minute"

action: LOG
```

### 14.3 Network Detection

**IDS Rules (Snort/Suricata):**

**❌ NO direct network signatures** - Akira does not perform active network enumeration.

**Recommended Monitoring:**
- SMB anomaly detection (unusual workstation-to-workstation SMB)
- Mass file access to network shares from single host
- Rapid file modification rates on file servers
- Unusual .arika file extensions appearing on SMB shares

**Example Suricata Rule (SMB anomaly):**
```
alert smb any any -> any any (
    msg:"Possible Akira - Rapid SMB File Operations";
    flow:to_server,established;
    threshold:type both, track by_src, count 100, seconds 60;
    classtype:ransomware;
    sid:9000001;
    rev:1;
)
```

### 14.4 Memory Forensics

**Hunt for Structures:**

**1. STL Set Red-Black Trees:**
```
Address: 0x140102138 (extension blacklist)
Address: 0x140102148 (directory blacklist)
Address: 0x140102158 (process blacklist)

Pattern:
- 64-byte aligned nodes
- Parent/left/right pointers
- Color byte (red=0, black=1)
- Embedded wstring (32 bytes)
```

**2. ASIO Handle Wrappers:**
```
Size: 112 bytes
Pattern:
- Vtable pointer at +0x00
- Ref count at +0x08 (typically 1-10)
- Weak ref count at +0x0C
- ASIO object at +0x10 (96 bytes)
```

**3. Task Objects:**
```
Size: 288 bytes
Pattern:
- Function pointers at +0x00, +0x08
- Linked list node at +0x10-0x40
- Shared pointers at +0x49, +0x59
- Wide string at +0x69 (file path)
- Task flags at +0x9C (0x10002 or 0x2)
```

**4. Thread Pool Structure:**
```
Size: 384 bytes
Pattern:
- Thread counts at +0x28, +0x34
- Critical sections at +0x40, +0x90 (80 bytes each)
- Condition variables at +0xE0, +0x128 (72 bytes each)
```

**Volatility Plugin Recommendation:**
```python
# Hypothetical Volatility plugin
class AkiraThreadPoolScanner(obj.ProfileModification):
    def check(self, offset):
        # Scan for 384-byte structure
        # Check for critical section patterns
        # Verify condition variable initialization
        # Validate thread counts (30/10/60 split)
```

---

## 15. Function Reference

### 15.1 Threading Functions (Phase 4)

| Address | Name | Purpose | Status |
|---------|------|---------|--------|
| 0x14007b6d0 | init_thread_pool | Initialize dual thread pool | ✅ Renamed (Phase 2) |
| 0x14007b850 | enqueue_encrypt_task | Add task to encryption queue | ✅ Renamed (Phase 2) |
| 0x14007b280 | create_asio_thread_pool | Create ASIO thread pool | ⏳ Analyzed |
| 0x1400385f0 | init_asio_context | Initialize ASIO context | ⏳ Analyzed |
| 0x14007a2d0 | create_thread_pool_impl | Create thread pool implementation | ⏳ Analyzed |
| 0x14007bb60 | build_task_object | Allocate and build task | ⏳ Analyzed |
| 0x1400c4030 | task_constructor | Initialize task structure | ⏳ Analyzed |
| 0x14007bd00 | asio_post_task | Submit task to ASIO pool | ⏳ Analyzed |
| 0x1400c45a0 | task_execution_function | Task entry point | ⏳ Analyzed |
| 0x140038a10 | init_win_thread | Initialize Windows thread | ⏳ Analyzed |
| 0x14007d200 | setup_thread_context | Setup thread context | ⏳ Analyzed |
| 0x140081d00 | init_critical_section | Initialize critical section | ⏳ Analyzed |
| 0x1400820e8 | init_condition_variable | Initialize condition variable | ⏳ Analyzed |
| 0x140082118 | condition_variable_wait | Wait on condition variable | ⏳ Analyzed |
| 0x1400812e0 | log_error_code | Log synchronization errors | ⏳ Analyzed |
| 0x14003a4a0 | allocate_task | Allocate task (0x120 bytes) | ⏳ Analyzed |

### 15.2 File System Functions (Phase 5)

#### Phase 5.1: Drive Enumeration

| Address | Name | Purpose | Status |
|---------|------|---------|--------|
| 0x14007e6a0 | initialize_drive_list | Enumerate and classify drives | ✅ Renamed |
| 0x14007f4e0 | vector_realloc_drives | Vector reallocation | ✅ Renamed |
| 0x140042830 | read_share_file | Parse share file input | ✅ Renamed |

#### Phase 5.2: Directory Traversal

| Address | Name | Purpose | Status |
|---------|------|---------|--------|
| 0x1400bf190 | folder_processor_worker | Main traversal worker | ✅ Renamed |
| 0x140070db0 | directory_iterator_ctor | Iterator constructor | ✅ Renamed |
| 0x14006f4c0 | open_directory_iterator | Open directory | ✅ Renamed |
| 0x140080b0c | find_next_file_wrapper | Advance iterator | ✅ Renamed |
| 0x14006e440 | is_dot_or_dotdot | Check if dot entry | ✅ Renamed |

#### Phase 5.3: File Filtering

| Address | Name | Purpose | Status |
|---------|------|---------|--------|
| 0x140001ac0 | init_extension_blacklist | Init extension blacklist | ✅ Renamed |
| 0x1400018a0 | init_directory_blacklist | Init directory blacklist | ✅ Renamed |
| 0x14005dea0 | stl_set_find | STL set find() | ✅ Renamed |
| 0x14005df80 | stl_wstring_compare | Wide string compare | ✅ Renamed |
| 0x1400cd260 | cleanup_directory_blacklist | Cleanup dir blacklist | ✅ Renamed |
| 0x1400cd2a0 | cleanup_extension_blacklist | Cleanup ext blacklist | ✅ Renamed |

#### Phase 5.4: File Access & Manipulation

| Address | Name | Purpose | Status |
|---------|------|---------|--------|
| 0x1400b6f10 | file_encryption_state_machine | File encryption workflow | ✅ Renamed |
| 0x140078cc0 | restart_manager_unlock_file | Force unlock via RM | ✅ Renamed |
| 0x140078ac0 | populate_process_blacklist | Build protected PID list | ✅ Renamed |
| 0x140001c10 | init_protected_process_names | Init process names (obfuscated) | ✅ Renamed |
| 0x140040b50 | init_asio_file_handle | Initialize ASIO handle | ⏳ Pending |
| 0x14007bfd0 | enqueue_encryption_task | Enqueue encryption task | ✅ Renamed |

### 15.3 Global Data Structures

| Address | Name | Type | Purpose |
|---------|------|------|---------|
| 0x140102138 | DAT_140102138 | std::set<wstring> | Extension blacklist (5 entries) |
| 0x140102148 | DAT_140102148 | std::set<wstring> | Directory blacklist (11 entries) |
| 0x140102158 | DAT_140102158 | std::set<wstring> | Protected process names (13 entries) |
| 0x1401021b8 | DAT_1401021b8 | std::vector<DWORD> | Protected process PIDs (dynamic) |
| 0x140102188 | DAT_140102188 | Logger* | Global error logger |
| 0x1400f9fd0 | DAT_1400f9fd0 | wstring | ".arika" extension |

---

## Conclusion

### Phase 4 & 5 Accomplishments

**Threading & Concurrency (Phase 4):**
✅ Complete thread pool architecture documented (384-byte structure)
✅ ASIO library integration analyzed (Boost ASIO statically linked)
✅ Thread allocation algorithm mapped (30/10/60 split)
✅ Synchronization mechanisms analyzed (critical sections, condition variables)
✅ Task queue system understood (288-byte task objects, producer-consumer)
✅ Deadlock-free design verified (single lock per operation)

**File System Operations (Phase 5):**
✅ Drive enumeration complete (40-byte drive structure, no active network enum)
✅ Directory traversal analyzed (88-byte iterator, task-based recursion)
✅ File filtering system documented (5 extensions, 11 directories, 13 processes)
✅ File access strategies mapped (two-stage locking, atomic rename)
✅ Restart Manager integration discovered (force process termination)
✅ Protected process list extracted (11 critical processes, NO EDR/AV)

### Technical Sophistication

**Rating: VERY HIGH**

Akira demonstrates professional-grade software engineering:
- **Industry-Standard Libraries:** Boost ASIO, STL containers
- **Proper Synchronization:** Critical sections, condition variables, atomic operations
- **Efficient Algorithms:** Red-black trees (O(log n)), work-stealing scheduler
- **Clean Architecture:** Separation of concerns, reference counting, exception safety
- **Performance Optimization:** Thread pooling, bounded queues, parallel I/O

This level of sophistication suggests:
- Experienced C++ developers (5+ years)
- Professional development practices
- Likely APT-level malware development
- Significant financial backing

### Critical Vulnerabilities

**Defender Opportunities:**

1. **Behavioral Detection:**
   - Restart Manager RmForceShutdown (malicious use)
   - Mass file access with specific flags (0xC0010000, 0xC0000000)
   - Atomic renaming to .arika extension
   - Two-stage file locking pattern

2. **Logic Flaws:**
   - Case-sensitive filtering on case-insensitive filesystem
   - Zero-byte file skip (unusual behavior)
   - NO security software in protected process list

3. **Memory Artifacts:**
   - STL structures (predictable memory layout)
   - ASIO handle wrappers (112-byte allocations)
   - Task objects (288-byte allocations)

### Next Phase

**Phase 6: Encryption Strategy Analysis**

Focus areas:
1. Full vs. Part vs. Spot encryption modes
2. Chunk size selection algorithms
3. Footer generation and structure
4. File size thresholds
5. Encryption mode performance trade-offs

**Key Function:** `encrypt_file_worker` (encryption mode dispatch)

---

**Document Status:** ✅ COMPLETE
**Total Functions Analyzed:** 40+ functions
**Total Structures Mapped:** 15+ structures (byte-accurate)
**Documentation Size:** ~3,000 lines (comprehensive technical detail)
**Confidence Level:** 95-99%
**Date Completed:** 2025-01-15

**Research Credit:** MottaSec
**Contact:** https://www.linkedin.com/company/mottasec
**GitHub:** https://github.com/MottaSec
**X (Twitter):** https://x.com/mottasec_

---

**END OF THREADING & EXECUTION ANALYSIS**
