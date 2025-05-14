let deviceItems = [];

async function fetchItems() {
    const response = await fetch('/profile/devices'); 
    if (response.ok) {
        data = await response.json();
        console.log(data)
        deviceItems = data['items']
        
        renderItems();
    }
}

function renderItems() {
    const itemList = document.getElementById('itemList');
    itemList.innerHTML = '';

    deviceItems.forEach((item) => {
        const listItem = document.createElement('li');
        listItem.classList.add('item');

        const itemText = document.createElement('span');
        itemText.textContent = item.device_topic;  
        listItem.appendChild(itemText);

        const updateButton = document.createElement('button');
        updateButton.textContent = 'Update';
        updateButton.addEventListener('click', () => showUpdateForm(item.id, item.device_topic));
        listItem.appendChild(updateButton);

        const deleteButton = document.createElement('button');
        deleteButton.textContent = 'Delete';
        deleteButton.addEventListener('click', () => deleteItem(item.id));
        listItem.appendChild(deleteButton);

        itemList.appendChild(listItem);
    });
}

function showUpdateForm(itemId, currentName) {
    const newName = prompt('Update item name:', currentName);
    if (newName && newName !== currentName) {
        updateItem(itemId, newName);
    }
}

async function updateItem(itemId, newName) {
    const response = await fetch(`/profile/${itemId}`, {  // Corrected URL here for updating
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ device_topic: newName })
    });

    if (response.ok) {
        fetchItems();
    } else {
        alert('Failed to update item.');
    }
}

async function deleteItem(itemId) {
    const response = await fetch(`/profile/${itemId}`, {  
        method: 'DELETE'
    });

    if (response.ok) {
        fetchItems();
    } else {
        alert('Failed to delete item.');
    }
}

async function createItem() {
    const itemName = document.getElementById('createItemName').value.trim();
    if (itemName) {
        const response = await fetch('/profile', { 
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ device_topic: itemName })
        });

        if (response.ok) {
            fetchItems();
        } else {
            alert('Failed to create item.');
        }
    } else {
        alert('Please enter an item name.');
    }
}

document.getElementById('createButton').addEventListener('click', createItem);

window.onload = fetchItems;