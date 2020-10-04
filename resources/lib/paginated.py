import resources.lib.utils as utils


def get_next_page(response_headers=None):
    num_pages = utils.try_parse_int(response_headers.get('X-Pagination-Page-Count', 0))
    this_page = utils.try_parse_int(response_headers.get('X-Pagination-Page', 0))
    if this_page < num_pages:
        return [{'next_page': this_page + 1}]
    return []


class PaginatedItems():
    def __init__(self, items, page=None, limit=None):
        self.all_items = items or []
        self.limit = utils.try_parse_int(limit) or 20
        self.get_page(page)

    def get_page(self, page=None):
        self.page = utils.try_parse_int(page) or 1
        self.index_z = self.page * self.limit
        self.index_a = self.index_z - self.limit
        self.index_z = len(self.all_items) if len(self.all_items) < self.index_z else self.index_z
        self.items = self.all_items[self.index_a:self.index_z]
        self.headers = {
            'X-Pagination-Page-Count': -(-len(self.all_items) // self.limit),
            'X-Pagination-Page': self.page}
        self.next_page = get_next_page(self.headers)
        return self.items

    def json(self):
        return self.items

    def get_dict(self):
        return {'items': self.items, 'headers': self.headers}
